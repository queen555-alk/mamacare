# MamaCare AI Assistant

A health-education assistant for pregnant women and new mothers. It answers
questions **only from a set of guidance notes**, shows which note each answer came
from, and follows fixed safety rules for emergencies, mental-health crises, and
requests for diagnosis or medicine doses.

> **Medical note:** the guidance notes in `assistant/knowledge/` are paraphrased
> drafts based on WHO and Nigerian guidance. They have **not yet been reviewed by a
> clinician**. This project is a software-engineering demonstration and must not be
> used with real patients until a nurse, midwife or doctor has verified every note.

## How it works

```
question
   |
   v
1. Safety rules (fixed patterns, no AI)
      crisis      -> supportive message, seek help now
      emergency   -> "go to the nearest health facility now"
      diagnosis / medicine dose request -> polite refusal
   |  (none matched)
   v
2. Retrieval (BM25 keyword ranking over the guidance notes)
   |
   v
3. Is the best note relevant enough?  no -> "I don't have a reliable source"
                                          (or, if a symptom was described: "see a health worker today")
   |  yes
   v
4. Answer from the note(s) with their sources
      optional: an LLM rewrites the notes in simple language, using ONLY the notes
```

Design decisions:

- **Safety runs before everything else.** The language model is never consulted for an
  emergency, crisis or medicine question (there is a test for this).
- **Grounded answers.** Without an LLM the assistant returns the note itself. With an
  LLM, the prompt restricts it to the retrieved notes. If the LLM call fails, the
  assistant falls back to the note.
- **"I don't know" is a valid answer.** A minimum relevance score stops it guessing.
- **No question logging.** Questions can contain personal health details.
- **No required dependencies** for the assistant itself (plain Python).

## Evaluation

`python evaluation/run_eval.py` runs 36 labelled questions. They were split **before
tuning** into a `dev` group (used to choose the stopwords and the relevance threshold)
and a `test` group (never used for tuning).

| | dev (tuned on) | test (held out) |
|---|---|---|
| Right note ranked first | 10 / 10 | 8 / 9 |
| Emergency recognised | 2 / 2 | 4 / 4 |
| Crisis recognised | 1 / 1 | 1 / 1 |
| Diagnosis / dose refused | 2 / 2 | 2 / 2 |
| Off-topic correctly declined | 3 / 3 | 1 / 2 |

The sets are small and written by the author, so treat the numbers as an
indication, not proof. The assistant does not use an LLM in this evaluation, so it
measures the retrieval and the safety rules.

### Known limitations (found by the held-out questions)

- **Different words, same meaning are missed.** "When should I see a *nurse* after
  *giving birth*?" fails because the note says "health worker" and "delivery".
- **A single shared word can cause a wrong match.** "How do I treat a snake bite?"
  returned the malaria note because both contain "treat".
- Emergency and crisis detection use keyword patterns. They are deliberately
  over-cautious (for example, any mention of bleeding, or of not feeling the baby move,
  triggers the emergency reply even when the context is harmless). They can still miss
  unusual phrasing, and they only understand English.
- Regression tests for earlier misses are in `tests/test_safety_rules.py`. The patterns
  have **not** been reviewed by a clinician or by Pidgin/Hausa/Yoruba/Igbo speakers.
- An LLM answer containing a dose or a diagnosis-style sentence is discarded and the
  guidance note is returned instead.

### Future work

- Semantic search with embeddings (fixes both retrieval problems above).
- A relevance check by an LLM before answering.
- Support for Pidgin, Hausa, Yoruba and Igbo.
- Clinician review of every note, and a larger evaluation set written with a clinician.

## Web interface

`web/index.html` is a phone-first single page served by `main.py` at `/` (the old JSON
message is now at `/health`). Start the app, then open `http://127.0.0.1:8001/` on a
phone or in a browser. Tabs: **Home** (sign-up, week and trimester ring, due date, next
visit), **Visits** (mark visits done, overdue flags), **Ask** (the assistant, with a red
"Call 112" card for emergency and crisis replies), **Due date** (calculator that needs no
sign-up). The Home tab has a **How are you feeling today?** card: she writes in her own words, we
keep only the symptoms recognised (never the text), and fixed rules reply with a warning level
(danger sign: go to a facility now; severe or fever: speak to a health worker today; the same
symptom on 3 days in a week: mention it at the next visit). Endpoints: `POST` and `GET
/mothers/{id}/symptoms`. The rules in `assistant/symptoms.py` are drafts for a clinician to review.

From week 28 the Home tab also shows a **Get ready for the birth** checklist. Its seven
items come straight from the "Preparing for delivery" guidance note; ticks are saved on the
phone only and erased when the mother deletes her data.

Mothers create a profile with a phone number and a 6-digit PIN and stay signed in on
that phone for 30 days. Questions to the assistant are never stored.

## Sign-in and privacy

- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout` (see `/docs`). PINs are
  stored only as salted scrypt hashes; session tokens only as SHA-256 hashes.
- A mother can read, change or delete **only her own** records (`DELETE /mothers/{id}`
  erases her profile, visits and sign-in details).
- 5 wrong PINs lock that phone number for 15 minutes. Sign-in attempts are also limited
  per IP address.
- `GET /mothers` and `GET /missed` list everyone's names and phone numbers, so they are
  **health-worker only**. Set a long random key before starting the server and send it as
  the `X-Staff-Key` header:

  ```bash
  export MAMACARE_STAFF_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  ```

  If the variable is not set, those routes are switched off.
- The assistant is limited to 30 questions a minute per IP (`ASSISTANT_RATE_LIMIT`).
  Emergency and crisis messages are never limited.
- The old open `POST /mothers` route was removed. Profiles created before sign-in existed
  have no PIN, so mothers cannot sign in to them; health workers can still read them.
- Not done yet: PIN reset (needs SMS), HTTPS (put the app behind a TLS proxy before real
  use), and a clinician/legal review of the privacy approach under Nigeria's NDPA.

## Run it

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Open `http://127.0.0.1:8001/docs`, then use **POST /assistant/ask**:

```json
{"question": "How many antenatal visits should I have?"}
```

The response contains `kind` (`answer`, `emergency`, `crisis`, `refused`, `concern` or `no_source`),
the `answer`, and the `sources` used.

### Optional: connect a language model (Ollama or Anthropic)

Everything below is **off by default**. With no model configured the assistant works exactly
as before. When a model is configured it does four jobs, each fenced in by code:

| Step | What the model does | What stops it going wrong |
|---|---|---|
| Safety net | Re-reads each message for emergencies or crises the keyword rules missed (Pidgin, Yoruba, Hausa, Igbo, misspellings) | Runs only after the keyword rules, and can only **escalate**. Failure means "no opinion". |
| Note selector | Picks which guidance note fits, or "none" (fixes "nurse" vs "health worker", and the snake-bite false match) | Must return a real note id; the symptom check still applies. |
| Rewrite | Puts the note in short, simple words | Discarded if it has a dose, a diagnosis, a number not in the note, or no `[n]` citation. The note itself is shown instead. |
| Symptom reader | Reads free text (any of those languages) into symptom codes for the log | Can only **add** entries; unknown codes are dropped; warning rules are plain code. |

**Ollama** (no extra Python package needed):

```bash
export OLLAMA_MODEL="llama3.1:8b"          # any model you have pulled, or a cloud model name
# Ollama cloud only:
export OLLAMA_API_KEY="..."                 # keep this in your shell or a .env file, never in git or chat
# Your own Ollama server elsewhere (default is http://localhost:11434, or https://ollama.com with a key):
# export OLLAMA_HOST="http://192.168.1.20:11434"
```

**Anthropic**: `pip install anthropic`, `export ANTHROPIC_API_KEY=...` (optional `ASSISTANT_MODEL`,
`ASSISTANT_FAST_MODEL`). Force one with `ASSISTANT_PROVIDER=ollama|anthropic`.

Other settings: `ASSISTANT_TIMEOUT` (seconds per call, default 10), `ASSISTANT_RATE_LIMIT`
(model-assisted questions per minute per IP, default 30; **over the limit the assistant still
answers, just without the model**), `ASSISTANT_LOCAL_LANGUAGES=1` (let the rewrite answer in
Pidgin, Hausa, Yoruba or Igbo; **off by default** because those texts have not been reviewed).

**Privacy.** With a cloud model, the text of a question or symptom note leaves your server.
A local Ollama keeps it on your machine. Neither the questions nor the symptom text are stored
by MamaCare. Decide this before real mothers use the app, and check it against the NDPA.

**Honest status.** These calls were written without access to the live services. They are
tested with fake models and a fake local Ollama server (`tests/test_ai_layer.py`,
`tests/test_llm_providers.py`). Small local models follow JSON and "use only these notes"
instructions less reliably than large ones; the checks in code make failures safe, but
expect more fall-backs to the plain note. Measure it on your setup:

```bash
python evaluation/run_eval.py --ai -v
```

The `local` group in `evaluation/questions.json` holds five **draft** Pidgin cases that need a
Pidgin speaker or nurse to confirm before you trust them.

### Tests and evaluation

```bash
pytest
python evaluation/run_eval.py -v
```

## Files

```
assistant/
  __init__.py     the Assistant class: the flow above
  safety.py       crisis / emergency / refusal rules and fixed messages
  retrieval.py    BM25 search over the guidance notes
  llm.py          optional model steps: Ollama / Anthropic providers, prompts, JSON parsing
  symptoms.py     symptom log: keyword reader, model merge, fixed warning rules
  knowledge/      the guidance notes, one .md file each, with their source
ai_routes.py      FastAPI endpoints /assistant/ask and /assistant/sources
evaluation/       labelled questions and the evaluation script
tests/            unit tests
```
