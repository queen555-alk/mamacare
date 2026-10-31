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
