"""Retrieval: find which guidance note best matches a question.

We use BM25, a classic ranking method. It scores a note higher when it contains
the question's rare words, many times, without being very long. It needs no
external packages, so it is easy to read, test and explain.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "be", "been", "am", "do", "does", "did", "i",
    "my", "me", "you", "your", "it", "its", "this", "that", "these", "those",
    "can", "could", "should", "would", "will", "what", "when", "how", "why",
    "which", "who", "if", "so", "as", "by", "from", "have", "has", "had",
    "not", "no", "about", "any", "there", "than", "then", "also", "into",
    "after", "before", "during", "get", "much", "many", "need", "every",
    # Domain stopwords: nearly every note is about pregnancy, so these words
    # say nothing about WHICH note is relevant.
    "pregnant", "pregnancy",
}

# Different words for the same idea are mapped to one word, for questions AND
# notes, so "swollen feet" can match a note that says "swelling".
CANONICAL = {
    "swollen": "swelling",
    "fits": "convulsion", "seizure": "convulsion", "seizures": "convulsion",
    "convulsions": "convulsion", "convulsing": "convulsion",
    "vomit": "vomiting", "vomited": "vomiting", "throwing": "vomiting",
    "nauseous": "nausea", "morning": "nausea",
    "vaccination": "vaccine", "vaccinations": "vaccine", "vaccinated": "vaccine",
    "vaccines": "vaccine", "injection": "vaccine", "injections": "vaccine",
    "immunisation": "vaccine", "immunization": "vaccine",
    "immunisations": "vaccine", "immunizations": "vaccine",
    "tummy": "abdomen", "belly": "abdomen", "stomach": "abdomen",
    "abdominal": "abdomen",
    "babies": "baby", "infant": "baby", "kick": "movement", "kicks": "movement",
    "kicking": "movement", "moving": "movement", "moves": "movement",
    "move": "movement",
    "breastfeeding": "breastfeed", "breastfed": "breastfeed",
    "breastmilk": "breastfeed", "breast": "breastfeed",
    "delivering": "delivery", "deliver": "delivery", "birth": "delivery",
    "labor": "labour", "contractions": "labour",
    "tablets": "supplement", "tablet": "supplement", "pills": "supplement",
    "supplements": "supplement", "iron": "iron", "folate": "folic",
    "mosquitoes": "mosquito", "net": "mosquito", "nets": "mosquito",
    "herbs": "herbal", "herb": "herbal", "traditional": "herbal",
    "foods": "food", "eating": "food", "eat": "food", "diet": "food",
    "visits": "visit", "appointments": "visit", "appointment": "visit",
    "checkup": "visit", "clinic": "visit",
    "due": "due", "edd": "due",
}


def stem(word: str) -> str:
    """Very light stemming: 'bleeding', 'bleeds' -> 'bleed'."""
    if len(word) <= 3:
        return word
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in re.findall(r"[a-z]+", text.lower()):
        if raw in STOPWORDS:
            continue
        tokens.append(stem(CANONICAL.get(raw, raw)))
    return tokens


@dataclass
class Document:
    id: str
    title: str
    source: str
    status: str
    text: str


def load_documents(folder: Path) -> list[Document]:
    """Read every .md note. Format: header lines, a '---' line, then the body."""
    docs = []
    for path in sorted(Path(folder).glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        header, _, body = raw.partition("\n---\n")
        meta = {}
        for line in header.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip().lower()] = value.strip()
        docs.append(
            Document(
                id=path.stem,
                title=meta.get("title", path.stem),
                source=meta.get("source", "unknown"),
                status=meta.get("status", ""),
                text=body.strip(),
            )
        )
    return docs


class BM25Index:
    def __init__(self, docs: list[Document], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b
        # The title is counted twice so a note about "malaria" wins on malaria.
        self.doc_tokens = [tokenize(d.title) * 2 + tokenize(d.text) for d in docs]
        self.doc_freqs = [Counter(tokens) for tokens in self.doc_tokens]
        self.avg_len = sum(len(t) for t in self.doc_tokens) / max(len(docs), 1)
        df = Counter()
        for tokens in self.doc_tokens:
            df.update(set(tokens))
        n = len(docs)
        self.idf = {
            term: math.log(1 + (n - count + 0.5) / (count + 0.5))
            for term, count in df.items()
        }

    def search(self, query: str, k: int = 3) -> list[tuple[Document, float]]:
        query_tokens = tokenize(query)
        scored = []
        for doc, freqs, tokens in zip(self.docs, self.doc_freqs, self.doc_tokens):
            score = 0.0
            for term in query_tokens:
                if term not in freqs:
                    continue
                tf = freqs[term]
                norm = tf + self.k1 * (1 - self.b + self.b * len(tokens) / self.avg_len)
                score += self.idf[term] * tf * (self.k1 + 1) / norm
            if score > 0:
                scored.append((doc, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]
