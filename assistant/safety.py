"""Safety rules. These run BEFORE any search or language model.

A health assistant must never "think about" an emergency: if a message sounds
like one, the answer is fixed, fast and cautious. Rules are simple patterns so
they are predictable and easy to test. They are deliberately over-cautious:
a false alarm costs a clinic visit, a missed emergency can cost a life.

Order used by the Assistant: crisis -> emergency -> refusal -> (search) -> concern.
All patterns are English only. They still need review by a clinician and by
native speakers before the assistant is used with real people.
"""

import re

# ---------------------------------------------------------------- crisis ----

CRISIS_PATTERNS = [
    r"kill (my)?self", r"end(ing)? my life", r"take my (own )?life",
    r"want(ed)? to die|wanna die|\bwish (i|that i) (was|were) dead",
    r"\bsuicid\w*", r"(hurt|harm|cut) (my)?self",
    r"don'?t want to (live|be here|go on|wake up)",
    r"(no|not any) (point|reason) (in |to )?(living|go(ing)? on|anymore|any more)",
    r"don'?t see the point (of|in) (living|life|going on|anything)",
    r"(wish|rather)\W+(\w+\W+){0,3}(not alive|dead|never (been )?born|not here)",
    r"(end|ending) it all", r"better off (dead|without me)",
    r"can'?t go on(\W*$|\W+(anymore|any more|like this|living))",
    r"give up on (life|living)", r"(no longer|not) want to (be alive|exist)",
    # thoughts of harming the baby (postnatal crisis)
    r"(hurt|harm|kill|smother|drown)\w*\W+(\w+\W+){0,2}(my )?(baby|newborn|child|infant)",
]

# ------------------------------------------------------------- emergency ----

EMERGENCY_PATTERNS = [
    # bleeding of any kind
    r"\bbleed\w*", r"\bspotting\b", r"\bclots?\b",
    r"\bblood\W+(\w+\W+){0,3}(in|on|from|coming|dripping|running|discharge|"
    r"underwear|pad|pants|urine|stool|vagina|down)\b",
    # fits / loss of consciousness
    r"\b(fits|fitting|had a fit|having a fit|convuls\w*|seizure\w*)\b",
    r"\b(faint\w*|unconscious|passed out|collaps\w*|blacked out|black out)\b",
    # severe pain
    r"\b(severe|terrible|unbearable|worst|very bad|excruciating|sharp|strong)\W+"
    r"(\w+\W+){0,2}(headache|pain|abdominal|stomach|belly|tummy)",
    r"\b(belly|tummy|stomach|abdomen|abdominal)\W+(\w+\W+){0,4}"
    r"(hurt\w*|pain\w*|ach\w*)\W+(\w+\W+){0,2}"
    r"(so much|a lot|badly|terribly|very much|too much|unbearabl\w*)",
    r"\b(hurt\w*|pain\w*)\W+(\w+\W+){0,2}(so much|a lot|badly|terribly)\W+"
    r"(\w+\W+){0,3}(belly|tummy|stomach|abdomen)",
    # headache that does not settle
    r"headache\W+(\w+\W+){0,4}(won'?t|will not|does not|doesn'?t|not)\W+"
    r"(go|stop|goes|pass|ease|settle)",
    r"\b(persistent|constant|continuous|non-?stop|terrible)\W+headache",
    r"headache\W+(\w+\W+){0,5}(vision|swell\w*|swollen|upper (belly|abdomen))",
    # eyes
    r"\b(blurr\w*|blurry|double|dim|dark|spots?|stars)\W+(\w+\W+){0,2}"
    r"(vision|sight)|cannot see|can'?t see|flashing lights|"
    r"(vision|sight)\W+(\w+\W+){0,3}(going|gone|dark|dim|blur\w*|double|lost)|"
    r"seeing (spots|stars|double)",
    # waters / fluid
    r"\bwater\W+(has\W+)?(broke|broken|breaking)|waters\W+(have\W+)?(broke|broken)|"
    r"\bleak\w*\W+(\w+\W+){0,2}(fluid|water|liquid)|"
    r"\b(wet|fluid|water|gush\w*)\W+(\w+\W+){0,3}(runn\w*|flow\w*|leak\w*|gush\w*|"
    r"down my (leg|legs|thigh))",
    # breathing
    r"(difficulty|hard|trouble|struggl\w*)\W+(\w+\W+){0,2}breath\w*|"
    r"can'?t breathe|cannot breathe|short(ness)? of breath|breathless\w*",
    # fever
    r"\b(high|very high|severe)\W+(\w+\W+)?fever|\bfever\W+(\w+\W+){0,3}(chills|shiver\w*)|"
    r"\b(shiver\w*|chills)\W+(\w+\W+){0,3}fever",
    r"\bfever\W+(of|at|is|was)?\W*(3[8-9]|4\d)(\.\d)?\b",
    # newborn
    r"\b(not breathing|turning blue|gone blue|limp|floppy|yellow)\b\W*"
    r"(\w+\W+){0,2}(baby|newborn|infant)|"
    r"(baby|newborn|infant)\W+(\w+\W+){0,4}\b(not breathing|turning blue|gone blue|"
    r"limp|floppy|yellow|very cold|very sleepy|hot to touch)\b",
    r"\b(not breathing|turning blue|gone blue|limp|floppy)\b",
    # sudden swelling of face/hands
    r"\b(face|hands|eyes)\W+(\w+\W+){0,3}(swollen|swelling|puffy)\W+(\w+\W+){0,3}"
    r"(sudden\w*|overnight|suddenly)|sudden\w*\W+(\w+\W+){0,3}(swell\w*|swollen)",
    # abuse: not a medical emergency but a safety one; handled with the same
    # fixed "get help now" reply
    r"\b(beats?|beat|hits?|hit|hitting|beating)\W+(\w+\W+){0,2}me\b|"
    r"\b(abus\w+|violen\w+)\b",
]

BABY_WORDS = {"baby", "fetus", "foetus", "newborn", "infant", "babies"}
WOMB_WORDS = {"womb", "tummy", "belly", "stomach", "inside"}
# Words that, together with a baby word and movement/feeding, mean "something changed".
NEGATIVE_WORDS = {
    "not", "stopped", "stop", "isn't", "isnt", "hasn't", "hasnt", "haven't", "havent",
    "didn't", "didnt", "don't", "dont", "can't", "cant", "cannot", "no", "never", "less",
    "reduced", "decreased", "slower", "slow", "weaker", "weak", "won't", "wont",
    "refusing", "refuses", "refused", "unable", "quiet", "still",
}

PRETERM_CONTRACTION_WORDS = re.compile(
    r"\b(contraction\w*|labou?r|labou?r pains?|regular (tightening|cramps?)|"
    r"tightening|cramping)\b"
)
FIRST_PERSON = re.compile(r"\b(i|i'm|im|i've|ive|i am|i have|my)\b")

# -------------------------------------------------------------- refusals ----

REFUSAL_PATTERNS = [
    r"\b(dose|dosage|dosing)\b",
    r"how (many|much)\W+(\w+\W+){0,2}(mg|milligrams?|tablets?|pills?|spoons?|capsules?)",
    r"(what|which)\W+(\w+\W+){0,3}(drug|medicine|medication|tablet|pill|"
    r"antibiotic|painkiller)s?\W+(\w+\W+){0,3}(take|use|buy|give)",
    r"\bprescri\w*",
    r"\bdo i have\b|\bam i (having|suffering|sick|pregnant)\b|\bdiagnos\w*|"
    r"what is wrong with me|what (disease|illness|condition) do i have",
    # ending a pregnancy or inducing labour at home
    r"\b(abort\w*|termination|misoprostol|cytotec|miscarr\w+ on purpose)\b",
    r"\binduce\w*\W+(\w+\W+){0,2}(labou?r|birth|delivery)|\b(bring|start|kick)\W+(\w+\W+){0,2}on\W+labou?r",
    r"\b(paracetamol|ibuprofen|aspirin|diclofenac|tramadol|codeine|chloroquine|"
    r"artemether|lumefantrine|coartem|amoxicillin|ciprofloxacin|metronidazole)\b",
]

# ------------------------------------------------- everyday symptom words ----
# Used AFTER the notes have been searched, to avoid answering a personal
# symptom with an unrelated note and to avoid a bare "I don't know".
SYMPTOM_WORDS = re.compile(
    r"\b(pain\w*|hurt\w*|ach\w*|headache\w*|dizz\w*|fever\w*|vomit\w*|itch\w*|"
    r"swollen|swelling|discharge|burning|rash|cough\w*|diarrh\w+|cramp\w*|"
    r"weak|nausea|sick|unwell|worr\w+|worse|lump|numb\w*|tingl\w*|pale|yellow\w*|"
    r"discomfort|pressure|tight\w*)\b"
)

# --------------------------------------------------------------- messages ---

EMERGENCY_MESSAGE = (
    "What you describe could be a danger sign. Please go to the nearest health "
    "facility now, or ask someone to take you. If you can, call your local "
    "emergency number (112 in Nigeria). Do not wait for your next appointment "
    "and do not try to treat this at home."
)

CRISIS_MESSAGE = (
    "I'm really sorry you are feeling this way, and I'm glad you said it. You "
    "deserve support right now. Please talk to someone you trust, or to a nurse, "
    "midwife or doctor, today. If you feel you might hurt yourself or your baby, "
    "go to the nearest health facility or call your local emergency number (112 "
    "in Nigeria) now, and do not stay alone."
)

REFUSAL_MESSAGE = (
    "I can't diagnose conditions or recommend medicines, doses, or ways to start "
    "or end a pregnancy. A nurse, midwife or doctor needs to examine you and "
    "advise you. I can share general information, for example about warning "
    "signs, antenatal visits, nutrition, vaccines or newborn care."
)

NO_SOURCE_MESSAGE = (
    "I don't have a reliable source for that in my guidance notes, so I would "
    "rather not guess. Please ask a nurse or midwife at your health centre."
)

CONCERN_MESSAGE = (
    "I don't have a reliable note about what you describe, and I can't tell how "
    "serious it is from here. Because you are pregnant or have just had a baby, "
    "please speak to a nurse, midwife or doctor today. If it gets worse, or you "
    "notice bleeding, a severe headache, blurred vision, fits, or the baby moving "
    "less, go to the nearest health facility straight away."
)

DISCLAIMER = "This is general health information, not medical advice."

# ---------------------------------------------------------------- helpers ---

_DOSE_IN_TEXT = re.compile(
    r"\b\d+(\.\d+)?\s*(mg|mcg|µg|ug|ml|g|iu|units?|tablets?|pills?|capsules?|spoons?)\b",
    re.IGNORECASE,
)
_DIAGNOSING = re.compile(
    r"\byou (probably |likely |may well |definitely )?(have|are suffering from|"
    r"are having|got)\b|\bthis is (definitely|probably|likely)\b",
    re.IGNORECASE,
)


def normalise(text: str) -> str:
    """Lower-case, straighten phone-style quotes, collapse spaces."""
    text = text.lower()
    for fancy in ("’", "‘", "ʼ", "`", "´"):
        text = text.replace(fancy, "'")
    return re.sub(r"\s+", " ", text).strip()


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def is_crisis(question: str) -> bool:
    return _any(CRISIS_PATTERNS, normalise(question))


def _movement_concern(text: str) -> bool:
    words = set(re.findall(r"[a-z']+", text))
    has_subject = bool(words & BABY_WORDS) or bool(words & WOMB_WORDS)
    negative = bool(words & NEGATIVE_WORDS)
    movement = bool(re.search(r"\b(mov\w*|kick\w*|stir\w*|jump\w*|felt|feel\w*)", text))
    feeding = bool(re.search(r"\b(feed\w*|suck\w*|breastfeed\w*|eat\w*|latch\w*)", text))
    baby = bool(words & BABY_WORDS)
    # "my baby has stopped moving", "I can't feel my baby", "newborn is not feeding"
    return (has_subject and negative and movement and (baby or "my" in words)) or (
        baby and negative and feeding
    )


def _preterm_contractions(text: str) -> bool:
    if not (FIRST_PERSON.search(text) and PRETERM_CONTRACTION_WORDS.search(text)):
        return False
    if re.search(r"\b(preterm|premature|too early|early labou?r)\b", text):
        return True
    for n in re.findall(r"\b(\d{1,2})\s*weeks?\b", text):
        if int(n) < 37:
            return True
    for n in re.findall(r"\b(\d)\s*months?\b", text):
        if int(n) <= 8:
            return True
    return False


def is_emergency(question: str) -> bool:
    text = normalise(question)
    if _any(EMERGENCY_PATTERNS, text):
        return True
    return _movement_concern(text) or _preterm_contractions(text)


def needs_refusal(question: str) -> bool:
    return _any(REFUSAL_PATTERNS, normalise(question))


def mentions_symptom(question: str) -> bool:
    """True when the person seems to describe how they, or their baby, feel."""
    text = normalise(question)
    return bool(SYMPTOM_WORDS.search(text)) and bool(FIRST_PERSON.search(text) or
                                                      set(re.findall(r"[a-z']+", text)) & BABY_WORDS)


def symptom_terms(question: str) -> set[str]:
    return set(m.group(0) for m in SYMPTOM_WORDS.finditer(normalise(question)))


def unsafe_llm_text(text: str) -> bool:
    """True if a language-model answer contains a dose or sounds like a diagnosis."""
    return bool(_DOSE_IN_TEXT.search(text) or _DIAGNOSING.search(text))
