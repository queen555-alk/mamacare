"""Measure how well the assistant behaves on a fixed set of questions.

Run from the project folder:   python evaluation/run_eval.py
Add -v to see every question.   Exit code 1 if a safety case fails.

Two groups of questions are reported separately:
  dev  - used while tuning (synonyms, MIN_SCORE). Scores here are optimistic.
  test - written before tuning and never used to tune. This is the honest score.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant import Assistant  # noqa: E402

SAFETY_KINDS = {"emergency", "crisis", "refused"}


def main(verbose: bool = False) -> int:
    questions = json.loads((Path(__file__).parent / "questions.json").read_text())
    assistant = Assistant()  # no LLM: measures retrieval and safety rules only
    stats = defaultdict(lambda: defaultdict(int))
    safety_failures = 0

    for item in questions:
        split, q, expect = item["split"], item["question"], item["expect"]
        result = assistant.ask(q)
        got = result["kind"]
        ok = got == expect
        note = ""
        if expect == "answer":
            top3 = [d.id for d, _ in assistant.retrieve(q, 3)]
            stats[split]["answer_total"] += 1
            stats[split]["top3_hit"] += item["source"] in top3
            top1_ok = ok and result["sources"] and result["sources"][0]["id"] == item["source"]
            stats[split]["top1_hit"] += bool(top1_ok)
            ok = bool(top1_ok)
            note = f"want {item['source']}, got {[s['id'] for s in result['sources']] or got}"
        else:
            stats[split][expect + "_total"] += 1
            stats[split][expect + "_ok"] += ok
            if not ok:
                note = f"want {expect}, got {got}"
        if not ok and expect in SAFETY_KINDS:
            safety_failures += 1
        if verbose or not ok:
            print(f"[{'PASS' if ok else 'FAIL'}] ({split}) {q}  {note}")

    print()
    for split in ("dev", "test"):
        s = stats[split]
        print(f"== {split} ==")
        if s["answer_total"]:
            print(f"  answers: top-1 correct {s['top1_hit']}/{s['answer_total']}, "
                  f"correct note in top 3: {s['top3_hit']}/{s['answer_total']}")
        for kind in ("emergency", "crisis", "refused", "no_source"):
            if s[kind + "_total"]:
                print(f"  {kind}: {s[kind + '_ok']}/{s[kind + '_total']}")
    print(f"\nSafety failures (emergency/crisis/refused): {safety_failures}")
    return 1 if safety_failures else 0


if __name__ == "__main__":
    sys.exit(main(verbose="-v" in sys.argv))
