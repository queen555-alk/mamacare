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
sign-up). From week 28 the Home tab also shows a **Get ready for the birth** checklist. Its seven
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
pip install fastapi "uvicorn[standard]" sqlalchemy pytest httpx
uvicorn main:app --reload --port 8001
```

Open `http://127.0.0.1:8001/docs`, then use **POST /assistant/ask**:

```json
{"question": "How many antenatal visits should I have?"}
```

The response contains `kind` (`answer`, `emergency`, `crisis`, `refused`, `concern` or `no_source`),
the `answer`, and the `sources` used.

### Optional: let an LLM rewrite the answers

```bash
pip install anthropic
export ANTHROPIC_API_KEY="your-key"
```

Without a key the assistant still works and returns the guidance note directly.

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
  llm.py          optional LLM step (grounded prompt)
  knowledge/      the guidance notes, one .md file each, with their source
ai_routes.py      FastAPI endpoints /assistant/ask and /assistant/sources
evaluation/       labelled questions and the evaluation script
tests/            unit tests
```
