"""MamaCare health-education assistant.

Flow for every question:
  1. Safety rules (crisis, emergency, diagnosis/medicine requests): fixed replies.
  2. Retrieval: find the best guidance notes.
  3. If nothing matches well enough: say "I don't have a reliable source", or,
     if the person describes a symptom, tell them to see a health worker today.
  4. Otherwise answer from the notes (optionally rewritten by an LLM), with sources.
     An LLM answer that contains a dose or sounds like a diagnosis is discarded.
"""

import logging
from pathlib import Path

from . import safety
from .llm import make_llm
from .retrieval import BM25Index, load_documents, tokenize

log = logging.getLogger("mamacare.assistant")

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# Below this BM25 score the best note is treated as "not really about this".
# Chosen from the DEV questions only: off-topic questions scored at most 2.11,
# real questions at least 3.32, so 2.7 sits in the gap (see evaluation/run_eval.py).
MIN_SCORE = 2.7


class Assistant:
    def __init__(self, knowledge_dir: Path = KNOWLEDGE_DIR, llm=None, min_score: float = MIN_SCORE):
        self.docs = load_documents(knowledge_dir)
        self.index = BM25Index(self.docs)
        self.llm = llm
        self.min_score = min_score

    @classmethod
    def default(cls) -> "Assistant":
        return cls(llm=make_llm())

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

    def ask(self, question: str) -> dict:
        if safety.is_crisis(question):
            return {"kind": "crisis", "answer": safety.CRISIS_MESSAGE, "sources": []}

        if safety.is_emergency(question):
            danger = next((d for d in self.docs if d.id == "danger_signs_pregnancy"), None)
            return {
                "kind": "emergency",
                "answer": safety.EMERGENCY_MESSAGE,
                "sources": [self._source(danger)] if danger else [],
            }

        if safety.needs_refusal(question):
            return {"kind": "refused", "answer": safety.REFUSAL_MESSAGE, "sources": []}

        symptomatic = safety.mentions_symptom(question)
        hits = [(d, s) for d, s in self.retrieve(question, 3) if s >= self.min_score]
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
        if self.llm is not None:
            try:
                text = self.llm(question, [d.text for d in used]) or None
                if text and safety.unsafe_llm_text(text):
                    log.warning("LLM answer rejected by safety check; using the note")
                    text = None
            except Exception:  # network, quota, anything: fall back safely
                log.exception("LLM call failed; using the guidance note directly")
        if text is None:
            text = best_doc.text
            used = [best_doc]

        return {
            "kind": "answer",
            "answer": f"{text}\n\n{safety.DISCLAIMER}",
            "sources": [self._source(d) for d in used],
        }
