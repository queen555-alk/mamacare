"""The AI steps, tested with fake models. They prove the fences hold: the model can only
make replies more cautious, and anything it gets wrong falls back to the safe behaviour."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from assistant import Assistant, safety
from assistant.llm import parse_json

VISITS = "How many antenatal visits should I have?"


def boom(*args):
    raise AssertionError("this AI step must not run")


# ------------------------------------------------------------ safety net ---

def test_triage_catches_what_the_keyword_rules_miss():
    bot = Assistant(triage=lambda q: "emergency")
    assert bot.ask("belle dey pain me well well")["kind"] == "emergency"
    bot = Assistant(triage=lambda q: "crisis")
    assert bot.ask("mi o fe gbe mo")["kind"] == "crisis"


def test_triage_never_runs_when_keyword_rules_already_fired():
    bot = Assistant(triage=boom)
    assert bot.ask("I am bleeding heavily")["kind"] == "emergency"
    assert bot.ask("I want to end my life")["kind"] == "crisis"


def test_triage_saying_none_cannot_cancel_a_keyword_emergency():
    bot = Assistant(triage=lambda q: None)
    assert bot.ask("I am bleeding heavily")["kind"] == "emergency"


@pytest.mark.parametrize("bad", ["banana", "", "EMERGENCYYY", 42, ["emergency"]])
def test_garbage_from_triage_is_ignored(bad):
    bot = Assistant(triage=lambda q, bad=bad: bad)
    assert bot.ask(VISITS)["kind"] == "answer"


def test_triage_failure_is_ignored():
    def broken(q):
        raise RuntimeError("network down")

    assert Assistant(triage=broken).ask(VISITS)["kind"] == "answer"


# ------------------------------------------------------- note selector ---

def test_selector_fixes_a_wording_mismatch():
    plain = Assistant()
    assert plain.ask("When should I see a nurse after giving birth?")["kind"] == "no_source"
    smart = Assistant(selector=lambda q, docs: "postnatal_care")
    result = smart.ask("When should I see a nurse after giving birth?")
    assert result["kind"] == "answer" and result["sources"][0]["id"] == "postnatal_care"


def test_selector_none_stops_a_wrong_match():
    assert Assistant().ask("How do I treat a snake bite?")["kind"] == "answer"   # the known keyword failure
    result = Assistant(selector=lambda q, docs: "none").ask("How do I treat a snake bite?")
    assert result["kind"] == "no_source"


def test_selector_unknown_id_or_failure_falls_back_to_keyword_search():
    assert Assistant(selector=lambda q, d: "not_a_real_note").ask(VISITS)["sources"][0]["id"] == "antenatal_schedule"
    assert Assistant(selector=lambda q, d: None).ask(VISITS)["sources"][0]["id"] == "antenatal_schedule"

    def broken(q, d):
        raise RuntimeError("x")

    assert Assistant(selector=broken).ask(VISITS)["sources"][0]["id"] == "antenatal_schedule"


def test_selector_cannot_bypass_the_symptom_check():
    # the chosen note must actually mention the symptom the person described
    bot = Assistant(selector=lambda q, docs: "iron_folic_acid")
    assert bot.ask("my baby has diarrhoea")["kind"] == "concern"


def test_selector_never_runs_for_emergency_crisis_or_refusal():
    bot = Assistant(selector=boom, llm=boom)
    for text in ["I am bleeding heavily", "I want to die", "What dose of paracetamol should I take?"]:
        assert bot.ask(text)["kind"] != "answer"


# ------------------------------------------------- rewriting and grounding ---

@pytest.mark.parametrize("draft, ok", [
    ("The WHO advises at least eight visits [1].", True),
    ("Plan 8 visits, starting early [1].", True),                       # digit form of a number in the note
    ("Go at 12, 20 and 26 weeks [1].", True),
    ("Go 11 times [1].", False),                                       # invented number
    ("The WHO advises at least eight visits.", False),                 # no citation
    ("Eight visits [3].", False),                                      # cites a passage that does not exist
    ("Take 500 mg of iron [1].", False),                               # dose
    ("You probably have anaemia [1].", False),                         # diagnosis
])
def test_rewrite_is_checked_before_it_is_used(draft, ok):
    result = Assistant(llm=lambda q, p: draft).ask(VISITS)
    assert result["kind"] == "answer"
    used_rewrite = "WHO advises" in result["answer"] or "Plan 8" in result["answer"] or "Go at 12" in result["answer"]
    assert used_rewrite == ok
    assert "[1]" not in result["answer"]                               # markers are removed
    if not ok:
        assert "eight antenatal contacts" in result["answer"]          # fell back to the note itself


def test_check_grounded_helper_directly():
    passages = ["Visit at 12 weeks and again at 20 weeks."]
    assert safety.check_grounded("Come at 12 weeks [1] and 20 weeks [1].", passages) == "Come at 12 weeks and 20 weeks."
    assert safety.check_grounded("Come at 13 weeks [1].", passages) is None
    assert safety.check_grounded("Come at 13 weeks [1].", passages, question="is 13 weeks ok?") is not None


# ---------------------------------------------------------- use_ai switch ---

def test_use_ai_false_skips_every_model_step():
    bot = Assistant(llm=boom, triage=boom, selector=boom)
    assert bot.ask(VISITS, use_ai=False)["kind"] == "answer"
    assert bot.urgency("belle dey pain me", use_ai=False) is None
    assert bot.ask("I am bleeding", use_ai=False)["kind"] == "emergency"


def test_a_full_set_of_working_fakes_gives_a_cited_answer():
    bot = Assistant(
        triage=lambda q: None,
        selector=lambda q, docs: "antenatal_schedule",
        llm=lambda q, p: "At least eight visits are advised [1].",
    )
    result = bot.ask(VISITS)
    assert result["kind"] == "answer" and "At least eight visits are advised." in result["answer"]
    assert result["sources"][0]["id"] == "antenatal_schedule"


# --------------------------------------------------------------- json helper ---

@pytest.mark.parametrize("raw, expected", [
    ('{"level": "emergency"}', {"level": "emergency"}),
    ('```json\n{"level": "none"}\n```', {"level": "none"}),
    ('Sure! {"note": "x"} hope that helps', {"note": "x"}),
    ("", None), ("no json here", None), ("{broken", None), ("[1, 2]", None),
])
def test_parse_json_is_forgiving_but_safe(raw, expected):
    assert parse_json(raw) == expected
