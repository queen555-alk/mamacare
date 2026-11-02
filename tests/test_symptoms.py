import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from assistant import safety, symptoms
from assistant.symptoms import assess, merge, parse, parse_keywords

TODAY = date(2026, 11, 2)


def entries(text):
    return {e["symptom"]: e["severity"] for e in parse_keywords(text)}


# ---------------------------------------------------------- keyword parsing ---

def test_everyday_symptoms_are_found():
    assert entries("I have a headache and some nausea") == {"headache": "moderate", "nausea": "moderate"}
    assert entries("my back hurts") == {"back_pain": "moderate"}
    assert entries("my back is hurting again") == {"back_pain": "moderate"}
    assert entries("I have pain in my lower back") == {"back_pain": "moderate"}
    assert entries("I will back my friend up") == {}
    assert entries("feeling very tired, plus heartburn") == {"tiredness": "moderate", "heartburn": "moderate"}


def test_severity_is_judged_clause_by_clause():
    assert entries("a little nausea but a severe headache") == {"nausea": "mild", "headache": "severe"}
    assert entries("mild headache") == {"headache": "mild"}


def test_danger_signs_are_found_in_natural_wording():
    assert "bleeding" in entries("there is blood in my underwear")
    assert "bleeding" in entries("I saw some spotting")
    assert "reduced_movement" in entries("my baby is not kicking like before")
    assert "blurred_vision" in entries("my vision is blurry")
    assert "convulsions" in entries("I had a fit this morning")
    assert "leaking_fluid" in entries("my waters broke")
    assert "breathlessness" in entries("I am short of breath")
    assert "high_fever" in entries("I have a high fever") and "fever" not in entries("I have a high fever")


def test_plain_words_do_not_invent_symptoms():
    assert entries("How can I keep fit during pregnancy?") == {}
    assert entries("I feel fine today, thank you") == {}
    assert entries("") == {}


# ------------------------------------------------------------ merging a model ---

def test_model_entries_are_added_and_bad_ones_dropped():
    kw = [{"symptom": "headache", "severity": "mild"}]
    ai = [
        {"symptom": "dizziness", "severity": "severe"},
        {"symptom": "made_up", "severity": "mild"},          # unknown code
        {"symptom": "nausea", "severity": "extreme"},        # unknown severity -> moderate
        "junk", None, {"severity": "mild"},                  # malformed
    ]
    out = {e["symptom"]: e["severity"] for e in merge(kw, ai)}
    assert out == {"headache": "mild", "dizziness": "severe", "nausea": "moderate"}


def test_the_model_can_raise_but_never_lower_a_severity():
    kw = [{"symptom": "headache", "severity": "severe"}]
    assert merge(kw, [{"symptom": "headache", "severity": "mild"}])[0]["severity"] == "severe"
    kw = [{"symptom": "headache", "severity": "mild"}]
    assert merge(kw, [{"symptom": "headache", "severity": "severe"}])[0]["severity"] == "severe"


def test_keyword_entries_survive_a_model_that_fails_or_returns_nothing():
    def broken(text):
        raise RuntimeError("down")

    assert {e["symptom"] for e in parse("I have a headache", broken)} == {"headache"}
    assert {e["symptom"] for e in parse("I have a headache", lambda t: None)} == {"headache"}
    assert {e["symptom"] for e in parse("I have a headache", lambda t: [])} == {"headache"}


def test_the_model_can_understand_other_languages():
    fake = lambda text: [{"symptom": "abdominal_pain", "severity": "moderate"}]
    assert [e["symptom"] for e in parse("belle dey pain me", fake)] == ["abdominal_pain"]


# ------------------------------------------------------------ warning rules ---

def level(new, history=(), today=TODAY):
    return assess([{"symptom": c, "severity": s} for c, s in new], list(history), today)["level"]


@pytest.mark.parametrize("code", ["bleeding", "reduced_movement", "convulsions", "blurred_vision",
                                  "leaking_fluid", "breathlessness", "high_fever"])
def test_every_danger_sign_is_urgent(code):
    result = assess([{"symptom": code, "severity": "mild"}], [], TODAY)
    assert result["level"] == "urgent" and result["message"] == safety.EMERGENCY_MESSAGE


def test_severe_headache_or_belly_pain_is_urgent_but_mild_is_not():
    assert level([("headache", "severe")]) == "urgent"
    assert level([("abdominal_pain", "severe")]) == "urgent"
    assert level([("headache", "mild")]) == "ok"
    assert level([("abdominal_pain", "moderate")]) == "ok"


def test_headache_with_swelling_or_dizziness_is_urgent():
    assert level([("headache", "mild"), ("swelling", "mild")]) == "urgent"
    assert level([("headache", "mild"), ("dizziness", "mild")]) == "urgent"


def test_fever_or_any_other_severe_symptom_means_see_a_worker_today():
    assert level([("fever", "mild")]) == "soon"
    assert level([("back_pain", "severe")]) == "soon"
    assert "leftover medicines" in assess([{"symptom": "fever", "severity": "mild"}], [], TODAY)["message"]


def test_the_same_symptom_on_three_days_in_a_week_prompts_a_mention():
    hist = [("nausea", TODAY - timedelta(days=1)), ("nausea", TODAY - timedelta(days=3))]
    result = assess([{"symptom": "nausea", "severity": "mild"}], hist, TODAY)
    assert result["level"] == "mention" and "3 days" in result["message"]
    # two days is not enough, and old entries do not count
    assert level([("nausea", "mild")], hist[:1]) == "ok"
    old = [("nausea", TODAY - timedelta(days=9)), ("nausea", TODAY - timedelta(days=10))]
    assert level([("nausea", "mild")], old) == "ok"
    # the same day twice counts once
    assert level([("nausea", "mild")], [("nausea", TODAY), ("nausea", TODAY)]) == "ok"


def test_urgent_beats_everything_else():
    hist = [("nausea", TODAY - timedelta(days=1)), ("nausea", TODAY - timedelta(days=2))]
    assert level([("nausea", "mild"), ("bleeding", "mild"), ("fever", "mild")], hist) == "urgent"


def test_every_symptom_has_a_label_and_a_keyword_pattern_or_is_model_only():
    for code in symptoms.SYMPTOM_CODES:
        assert symptoms.label(code)
    # every code except reduced_movement (handled in code) has a keyword pattern
    assert set(symptoms.SYMPTOM_CODES) - set(symptoms._PATTERNS) == {"reduced_movement"}
