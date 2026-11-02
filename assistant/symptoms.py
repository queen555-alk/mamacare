"""Symptom logging: turn what a mother writes into structured entries, then apply
fixed warning rules.

Only the structured result (symptom code, severity, time) is ever stored. The text
she typed is NOT stored, because it can contain private details.

A language model may help read free text (including Pidgin, Yoruba, Hausa or Igbo),
but it can only ADD entries. Entries found by the keyword rules always stay, and the
warning rules below are plain code, never the model. Rules are drafts: a clinician
must review them before real use.
"""

import re
from datetime import date, timedelta

from . import safety

# code -> (label shown to the mother, is a pregnancy danger sign)
SYMPTOMS: dict[str, tuple[str, bool]] = {
    "bleeding": ("Vaginal bleeding", True),
    "reduced_movement": ("Baby moving less", True),
    "convulsions": ("Fits or convulsions", True),
    "blurred_vision": ("Blurred vision", True),
    "leaking_fluid": ("Fluid leaking from the vagina", True),
    "breathlessness": ("Difficulty breathing", True),
    "high_fever": ("High fever", True),
    "headache": ("Headache", False),
    "abdominal_pain": ("Belly pain", False),
    "swelling": ("Swelling", False),
    "dizziness": ("Dizziness", False),
    "fever": ("Fever", False),
    "nausea": ("Nausea", False),
    "vomiting": ("Vomiting", False),
    "back_pain": ("Back pain", False),
    "tiredness": ("Tiredness", False),
    "heartburn": ("Heartburn", False),
    "constipation": ("Constipation", False),
}
SYMPTOM_CODES = tuple(SYMPTOMS)
SEVERITIES = ("mild", "moderate", "severe")
_RANK = {s: i for i, s in enumerate(SEVERITIES)}

# These are danger signs when severe, even though they are everyday symptoms when mild
# (see the "Danger signs in pregnancy" note: severe headache, severe abdominal pain).
SEVERE_IS_URGENT = {"headache", "abdominal_pain"}

_PATTERNS = {
    "bleeding": r"\bbleed\w*|\bspotting\b|\bblood\W+(\w+\W+){0,3}(in|on|from|coming|dripping|underwear|pad|pants)\b",
    "convulsions": r"\b(fits|had a fit|having a fit|convuls\w*|seizure\w*)\b",
    "blurred_vision": (r"\b(blurr\w*|blurry|double|dim|dark)\W+(\w+\W+){0,2}(vision|sight)|"
                       r"\b(vision|sight)\W+(\w+\W+){0,3}(going|gone|dark|dim|blur\w*|double|lost)|"
                       r"cannot see|can'?t see|flashing lights|seeing (spots|stars|double)"),
    "leaking_fluid": r"\bwater\W+(has\W+)?(broke|broken|breaking)|waters\W+(have\W+)?(broke|broken)|\bleak\w*\W+(\w+\W+){0,2}(fluid|water|liquid)",
    "breathlessness": r"short(ness)? of breath|can'?t breathe|cannot breathe|(difficulty|trouble|hard)\W+(\w+\W+){0,2}breath\w*|breathless\w*",
    "high_fever": r"\b(high|very high|severe)\W+(\w+\W+)?fever|\bfever\W+(of|at|is|was)?\W*(3[89]|4\d)\b",
    "headache": r"head\W?ache|\bhead\W+(\w+\W+){0,2}(pain\w*|hurt\w*)",
    "abdominal_pain": r"\b(belly|tummy|stomach|abdomen|abdominal)\W+(\w+\W+){0,3}(pain\w*|hurt\w*|ach\w*|cramp\w*)|\b(pain|ache)\W+(\w+\W+){0,3}(belly|tummy|stomach|abdomen)",
    "swelling": r"\bswollen\b|\bswelling\b|\bpuffy\b",
    "dizziness": r"\bdizz\w*|light-?headed",
    "fever": r"\bfever\w*|\bhot body\b",
    "nausea": r"\bnause\w*|morning sickness",
    "vomiting": r"\bvomit\w*|throwing up",
    "back_pain": r"\bback\W+(\w+\W+){0,2}(pain\w*|ache\w*|hurt\w*)|\bbackache\b|\b(pain|ache)\w*\W+(\w+\W+){0,3}(in|at)\W+(my |the )?(lower )?back\b",
    "tiredness": r"\btired\w*|\bexhaust\w*|\bfatigue\w*",
    "heartburn": r"heartburn|acid reflux|burning (in )?(my )?chest",
    "constipation": r"constipat\w*",
}
_SEVERE = re.compile(r"\b(severe|severely|terrible|terribly|unbearable|worst|very bad|excruciating|strong|sharp)\b")
_MILD = re.compile(r"\b(mild|slight|slightly|little|small|bit)\b")


def _clauses(text: str) -> list[str]:
    """Split so 'a little nausea but severe headache' is judged clause by clause."""
    return [c for c in re.split(r"[.;!?\n]|,| but | and | although | though ", text) if c.strip()]


def _severity_of(clause: str) -> str:
    if _SEVERE.search(clause):
        return "severe"
    if _MILD.search(clause):
        return "mild"
    return "moderate"


def parse_keywords(text: str) -> list[dict]:
    """Find symptoms with fixed patterns. English only."""
    found: dict[str, str] = {}
    norm = safety.normalise(text)
    for clause in _clauses(norm):
        sev = _severity_of(clause)
        for code, pattern in _PATTERNS.items():
            if re.search(pattern, clause):
                found[code] = max(found.get(code, sev), sev, key=_RANK.get)
    if safety._movement_concern(norm):
        found["reduced_movement"] = "severe"
    # a more specific code replaces the general one
    if "high_fever" in found:
        found.pop("fever", None)
    return [{"symptom": c, "severity": s} for c, s in found.items()]


def merge(keyword_entries: list[dict], ai_entries) -> list[dict]:
    """Keep every keyword entry. Add valid model entries. Invalid ones are dropped."""
    merged = {e["symptom"]: e["severity"] for e in keyword_entries}
    for item in ai_entries or []:
        try:
            code, sev = item["symptom"], item.get("severity", "moderate")
        except (TypeError, KeyError, AttributeError):
            continue
        if code not in SYMPTOMS:
            continue
        if sev not in SEVERITIES:
            sev = "moderate"
        merged[code] = max(merged.get(code, sev), sev, key=_RANK.get)
    return [{"symptom": c, "severity": s} for c, s in merged.items()]


def parse(text: str, ai_parser=None) -> list[dict]:
    """Entries from keyword rules, plus the model's reading when a parser is given."""
    keyword = parse_keywords(text)
    ai = None
    if ai_parser is not None:
        try:
            ai = ai_parser(text)
        except Exception:  # network, quota, bad output: keyword result still stands
            ai = None
    return merge(keyword, ai)


def label(code: str) -> str:
    return SYMPTOMS[code][0]


# ----------------------------------------------------------- warning rules ---

MENTION_DAYS_NEEDED = 3   # same symptom on this many different days...
MENTION_WINDOW_DAYS = 7   # ...within this many days


def assess(new_entries: list[dict], history: list[tuple[str, date]], today: date | None = None) -> dict:
    """Decide how worried to be. `history` is earlier (symptom_code, day) pairs.

    Returns {"level": "urgent" | "soon" | "mention" | "ok", "message": str}.
    """
    today = today or date.today()
    codes = {e["symptom"]: e["severity"] for e in new_entries}

    if any(SYMPTOMS[c][1] for c in codes):
        return {"level": "urgent", "message": safety.EMERGENCY_MESSAGE}
    if any(sev == "severe" and c in SEVERE_IS_URGENT for c, sev in codes.items()):
        return {"level": "urgent", "message": safety.EMERGENCY_MESSAGE}
    # headache together with swelling or dizziness is the pattern the pre-eclampsia note warns about
    if "headache" in codes and ({"swelling", "dizziness"} & set(codes)):
        return {"level": "urgent", "message": safety.EMERGENCY_MESSAGE}

    if "fever" in codes or any(sev == "severe" for sev in codes.values()):
        return {"level": "soon", "message": (
            "Please speak to a nurse, midwife or doctor today about this. Do not treat a fever "
            "yourself with leftover medicines. If it gets worse, or you notice bleeding, a "
            "severe headache, blurred vision, fits, or the baby moving less, go to a health "
            "facility straight away.")}

    since = today - timedelta(days=MENTION_WINDOW_DAYS - 1)
    for code in codes:
        days = {d for c, d in history if c == code and since <= d <= today} | {today}
        if len(days) >= MENTION_DAYS_NEEDED:
            return {"level": "mention", "message": (
                f"You have noted {label(code).lower()} on {len(days)} days this week. Tell your "
                "health worker at your next visit, or go sooner if it gets worse.")}

    return {"level": "ok", "message": "Saved. Tell your health worker at your next visit if anything worries you."}
