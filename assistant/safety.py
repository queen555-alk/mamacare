"""Safety rules. These run BEFORE any search or language model.

A health assistant must never "think about" an emergency: if a message sounds
like one, the answer is fixed, fast and cautious. Rules are simple patterns so
they are predictable and easy to test. They are deliberately over-cautious:
a false alarm costs a clinic visit, a missed emergency can cost a life.
"""

import re

CRISIS_PATTERNS = [
    r"kill myself", r"end my life", r"want to die", r"\bsuicid\w*",
    r"hurt myself", r"harm myself", r"don'?t want to live",
]

EMERGENCY_PATTERNS = [
    r"\bbleed\w*",
    r"\b(fits|fitting|had a fit|having a fit|convuls\w*|seizure\w*)\b",
    r"\b(faint\w*|unconscious|passed out|collaps\w*)\b",
    r"\b(severe|terrible|unbearable|worst|very bad)\W+(\w+\W+){0,2}"
    r"(headache|pain|abdominal|stomach|belly)",
    r"\b(blurr\w*|blurry)\W+(vision|sight)|cannot see|can'?t see|flashing lights",
    r"\bwater\W+(has\W+)?(broke|broken|breaking)|waters\W+broke|"
    r"\bleak\w*\W+(\w+\W+){0,2}(fluid|water|liquid)",
    r"(difficulty|hard|trouble|struggl\w*)\W+(\w+\W+){0,2}breath\w*|"
    r"can'?t breathe|cannot breathe|short(ness)? of breath",
    r"\b(high|very high|severe)\W+(\w+\W+)?fever",
    r"\b(not breathing|turning blue|gone blue|limp|floppy)\b",
]

# "my baby has stopped moving" needs two ideas together, so it is checked in code.
BABY_WORDS = {"baby", "fetus", "foetus", "newborn", "infant"}
NEGATIVE_WORDS = {"not", "stopped", "stop", "isn't", "hasn't", "no", "less",
                  "reduced", "decreased", "won't", "wont", "refusing", "refuses"}

REFUSAL_PATTERNS = [
    r"\b(dose|dosage|dosing)\b",
    r"how (many|much)\W+(\w+\W+){0,2}(mg|milligrams?|tablets?|pills?|spoons?)",
    r"(what|which)\W+(\w+\W+){0,3}(drug|medicine|medication|tablet|pill|"
    r"antibiotic|painkiller)s?\W+(\w+\W+){0,3}(take|use|buy|give)",
    r"\bprescri\w*",
    r"\bdo i have\b|\bam i (having|suffering|sick|pregnant)\b|\bdiagnos\w*|"
    r"what is wrong with me|what (disease|illness|condition) do i have",
]

EMERGENCY_MESSAGE = (
    "What you describe could be a danger sign. Please go to the nearest health "
    "facility now, or ask someone to take you. If you can, call your local "
    "emergency number (112 in Nigeria). Do not wait for your next appointment "
    "and do not try to treat this at home."
)

CRISIS_MESSAGE = (
    "I'm really sorry you are feeling this way, and I'm glad you said it. You "
    "deserve support right now. Please talk to someone you trust, or to a nurse, "
    "midwife or doctor, today. If you feel you might hurt yourself, go to the "
    "nearest health facility or call your local emergency number (112 in "
    "Nigeria) now, and do not stay alone."
)

REFUSAL_MESSAGE = (
    "I can't diagnose conditions or recommend medicines or doses. A nurse, "
    "midwife or doctor needs to examine you and advise you. I can share general "
    "information, for example about warning signs, antenatal visits, "
    "nutrition, vaccines or newborn care."
)

NO_SOURCE_MESSAGE = (
    "I don't have a reliable source for that in my guidance notes, so I would "
    "rather not guess. Please ask a nurse or midwife at your health centre."
)

DISCLAIMER = "This is general health information, not medical advice."


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def is_crisis(question: str) -> bool:
    return _any(CRISIS_PATTERNS, question.lower())


def is_emergency(question: str) -> bool:
    text = question.lower()
    if _any(EMERGENCY_PATTERNS, text):
        return True
    words = set(re.findall(r"[a-z']+", text))
    baby = bool(words & BABY_WORDS)
    negative = bool(words & NEGATIVE_WORDS)
    movement = bool(re.search(r"\b(mov\w*|kick\w*)", text))
    feeding = bool(re.search(r"\b(feed\w*|suck\w*|breastfeed\w*|eat\w*)", text))
    # "my baby has stopped moving", "newborn is not feeding"
    return baby and negative and (movement or feeding)


def needs_refusal(question: str) -> bool:
    return _any(REFUSAL_PATTERNS, question.lower())
