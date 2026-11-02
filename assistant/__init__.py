"""MamaCare health-education assistant.

Flow for every question:
<<<<<<< HEAD
  1. Safety rules (crisis, emergency, diagnosis/medicine requests): fixed replies.
  2. Retrieval: find the best guidance notes.
  3. If nothing matches well enough: say "I don't have a reliable source", or,
     if the person describes a symptom, tell them to see a health worker today.
  4. Otherwise answer from the notes (optionally rewritten by an LLM), with sources.
     An LLM answer that contains a dose or sounds like a diagnosis is discarded.
=======
  1. Keyword safety rules: crisis, emergency. Fixed replies, no AI.
  2. AI safety net (optional): a model re-reads the message and may ESCALATE to crisis
     or emergency. It can never cancel step 1 or make a reply less cautious.
  3. Keyword rules for diagnosis / medicine / pregnancy-ending requests: polite refusal.
  4. Retrieval: BM25 ranks the guidance notes; an optional model may pick the right note
     (or "none") when wording differs. Its choice must be a real note id.
  5. Nothing matches: "I don't have a reliable source", or, if the person describes a
     symptom, "see a health worker today".
  6. Otherwise answer from the note, optionally rewritten by a model. The rewrite is
     checked in code (no doses, no diagnoses, no invented numbers, must cite the notes)
     and replaced by the note itself if it fails.

Every AI step is a plain callable that may be None, and any failure in one is logged and
skipped. `use_ai=False` switches all of them off for a single call.
>>>>>>> 3a88354 (api model)
"""

import logging
from pathlib import Path

from . import safety
<<<<<<< HEAD
from .llm import make_llm
=======
from .llm import build_ai
>>>>>>> 3a88354 (api model)
from .retrieval import BM25Index, load_documents, tokenize

log = logging.getLogger("mamacare.assistant")

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# Below this BM25 score the best note is treated as "not really about this".
# Chosen from the DEV questions only: off-topic questions scored at most 2.11,
# real questions at least 3.32, so 2.7 sits in the gap (see evaluation/run_eval.py).
MIN_SCORE = 2.7


class Assistant:
    def __init__(self, knowledge_dir: Path = KNOWLEDGE_DIR, llm=None, min_score: float = MIN_SCORE,
                 triage=None, selector=None, symptom_parser=None):
        self.docs = load_documents(knowledge_dir)
        self.index = BM25Index(self.docs)
        self.llm = llm
        self.triage = triage
        self.selector = selector
        self.symptom_parser = symptom_parser
        self.min_score = min_score

    @classmethod
    def default(cls) -> "Assistant":
        ai = build_ai() or {}
        return cls(llm=ai.get("llm"), triage=ai.get("triage"), selector=ai.get("selector"),
                   symptom_parser=ai.get("symptom_parser"))

    def retrieve(self, question: str, k: int = 3):
        return self.index.search(question, k)

    def sources(self) -> list[dict]:
        return [self._source(d) for d in self.docs]

    @staticmethod
    def _mentions_any(doc, terms: set[str]) -> bool:
        # same synonym/stem rules as the search, so "swollen" matches "swelling"
        doc_tokens = set(tokenize(doc.title + " " + doc.text))
        return any(tok in doc_tokens for t in terms for tok in tokenize(t))

    def _source(self, doc) -> dict:
        return {"id": doc.id, "title": doc.title, "source": doc.source}

    @staticmethod
    def _safe(step, *args):
        """Run an AI step; any failure means 'no opinion'. Never logs the person's text."""
        try:
            return step(*args)
        except Exception as err:
            log.warning("AI step failed (%s); continuing without it", type(err).__name__)
            return None

    # ---- fixed replies ----
    def _crisis(self) -> dict:
        return {"kind": "crisis", "answer": safety.CRISIS_MESSAGE, "sources": []}

    def _emergency(self) -> dict:
        danger = next((d for d in self.docs if d.id == "danger_signs_pregnancy"), None)
        return {
            "kind": "emergency",
            "answer": safety.EMERGENCY_MESSAGE,
            "sources": [self._source(danger)] if danger else [],
        }

    def urgency(self, text: str, use_ai: bool = True) -> str | None:
        """"crisis", "emergency" or None. Keyword rules first; the model can only escalate."""
        if safety.is_crisis(text):
            return "crisis"
        if safety.is_emergency(text):
            return "emergency"
        if use_ai and self.triage is not None:
            level = self._safe(self.triage, text)
            if level in ("crisis", "emergency"):
                return level
        return None

    def ask(self, question: str, use_ai: bool = True) -> dict:
        level = self.urgency(question, use_ai)
        if level == "crisis":
            return self._crisis()
        if level == "emergency":
            return self._emergency()

        if safety.needs_refusal(question):
            return {"kind": "refused", "answer": safety.REFUSAL_MESSAGE, "sources": []}

        symptomatic = safety.mentions_symptom(question)
<<<<<<< HEAD
        hits = [(d, s) for d, s in self.retrieve(question, 3) if s >= self.min_score]
=======
        scored = self.retrieve(question, 3)
        hits = [(d, s) for d, s in scored if s >= self.min_score]

        if use_ai and self.selector is not None:
            choice = self._safe(self.selector, question, self.docs)
            if choice == "none":
                hits = []
            elif choice is not None:
                chosen = next((d for d in self.docs if d.id == choice), None)
                if chosen is not None:
                    score = next((s for d, s in scored if d.id == chosen.id), self.min_score)
                    hits = [(chosen, max(score, self.min_score))]
            # None or an unknown id: keep the keyword-search result

>>>>>>> 3a88354 (api model)
        if symptomatic:
            # A personal symptom must not be answered by a note that never mentions it.
            terms = {t.lower() for t in safety.symptom_terms(question)}
            hits = [(d, s) for d, s in hits if self._mentions_any(d, terms)]
        if not hits:
            if symptomatic:
                return {"kind": "concern", "answer": safety.CONCERN_MESSAGE, "sources": []}
            return {"kind": "no_source", "answer": safety.NO_SOURCE_MESSAGE, "sources": []}

        best_doc, best_score = hits[0]
        used = [d for d, s in hits if s >= 0.6 * best_score]

        text = None
<<<<<<< HEAD
        if self.llm is not None:
            try:
                text = self.llm(question, [d.text for d in used]) or None
                if text and safety.unsafe_llm_text(text):
                    log.warning("LLM answer rejected by safety check; using the note")
                    text = None
            except Exception:  # network, quota, anything: fall back safely
                log.exception("LLM call failed; using the guidance note directly")
=======
        if use_ai and self.llm is not None:
            passages = [d.text for d in used]
            draft = self._safe(self.llm, question, passages) or None
            if draft:
                if safety.unsafe_llm_text(draft):
                    log.warning("Model answer rejected: dose or diagnosis wording")
                else:
                    text = safety.check_grounded(draft, passages, question)
                    if text is None:
                        log.warning("Model answer rejected: not grounded in the notes")
>>>>>>> 3a88354 (api model)
        if text is None:
            text = best_doc.text
            used = [best_doc]

        return {
            "kind": "answer",
            "answer": f"{text}\n\n{safety.DISCLAIMER}",
            "sources": [self._source(d) for d in used],
        }
