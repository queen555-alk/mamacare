import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import pregnancy as pg

TODAY = date(2026, 11, 7)


def weeks_ago(n, extra=0):
    return TODAY - timedelta(weeks=n, days=extra)


def test_lmp_rules_match_registration():
    assert pg.validate_lmp(TODAY, TODAY) == TODAY
    assert pg.validate_lmp(TODAY - timedelta(days=294), TODAY)           # exactly 42 weeks is allowed
    with pytest.raises(ValueError, match="future"):
        pg.validate_lmp(TODAY + timedelta(days=1), TODAY)
    with pytest.raises(ValueError, match="42 weeks"):
        pg.validate_lmp(TODAY - timedelta(days=295), TODAY)


def test_due_date_is_280_days_and_schedule_has_the_eight_who_visits():
    lmp = weeks_ago(14)
    assert pg.estimated_due_date(lmp) == lmp + timedelta(days=280)
    sched = pg.antenatal_schedule(lmp)
    assert [v["week"] for v in sched] == [12, 20, 26, 30, 34, 36, 38, 40]
    assert sched[0]["date"] == lmp + timedelta(weeks=12) and sched[-1]["date"] == pg.estimated_due_date(lmp)


def visits_registered_at(lmp):
    """Which visit numbers registration would have saved on TODAY."""
    return {v["visit"] for v in pg.antenatal_schedule(lmp) if v["date"] >= TODAY}


def test_registration_at_14_weeks_skips_the_12_week_visit():
    assert visits_registered_at(weeks_ago(14)) == {2, 3, 4, 5, 6, 7, 8}


def test_moving_the_date_later_updates_every_visit_and_adds_newly_future_ones():
    old, new = weeks_ago(14), weeks_ago(6)
    plan = pg.plan_resync(visits_registered_at(old), new, TODAY)
    assert set(plan["update"]) == {2, 3, 4, 5, 6, 7, 8}
    assert plan["update"][2] == new + timedelta(weeks=20)
    assert [v["visit"] for v in plan["create"]] == [1]                    # 12 weeks is now ahead of her
    assert plan["create"][0]["date"] == new + timedelta(weeks=12)


def test_moving_the_date_earlier_keeps_overdue_visits_and_never_removes_any():
    old, new = weeks_ago(14), weeks_ago(30)
    existing = visits_registered_at(old)
    plan = pg.plan_resync(existing, new, TODAY)
    assert set(plan["update"]) == existing                                # all kept, even those now overdue
    assert plan["update"][2] == new + timedelta(weeks=20) < TODAY         # now in the past, so it will show as overdue
    assert plan["create"] == []                                           # visit 1 would be in the past: not invented


def test_visits_she_never_had_that_are_still_in_the_past_are_not_invented():
    plan = pg.plan_resync(set(), weeks_ago(30), TODAY)
    assert {v["visit"] for v in plan["create"]} == {4, 5, 6, 7, 8}        # 30 weeks is today; earlier ones are past


def test_a_visit_dated_today_is_created():
    lmp = TODAY - timedelta(weeks=12)
    plan = pg.plan_resync(set(), lmp, TODAY)
    assert plan["create"][0]["visit"] == 1 and plan["create"][0]["date"] == TODAY


def test_same_date_is_a_no_op_for_existing_visits():
    lmp = weeks_ago(14)
    existing = visits_registered_at(lmp)
    plan = pg.plan_resync(existing, lmp, TODAY)
    expected = {v["visit"]: v["date"] for v in pg.antenatal_schedule(lmp)}
    assert plan["update"] == {n: expected[n] for n in existing} and plan["create"] == []
