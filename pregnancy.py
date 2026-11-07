"""Pregnancy date rules in plain Python (no web or database code), so they are easy to test.

Used by main.py for registration and for editing the last period date.
"""

from datetime import date, timedelta

ANTENATAL_WEEKS = [12, 20, 26, 30, 34, 36, 38, 40]   # WHO: eight contacts
MAX_LMP_AGE_DAYS = 294                                 # 42 weeks


def validate_lmp(value: date, today: date | None = None) -> date:
    """A last-period date must not be in the future and not more than 42 weeks ago."""
    today = today or date.today()
    if value > today:
        raise ValueError("LMP date cannot be in the future")
    if today - value > timedelta(days=MAX_LMP_AGE_DAYS):
        raise ValueError("LMP date is more than 42 weeks ago; please check it")
    return value


def estimated_due_date(lmp: date) -> date:
    return lmp + timedelta(days=280)


def antenatal_schedule(lmp: date) -> list:
    return [
        {"visit": number, "week": weeks, "date": lmp + timedelta(weeks=weeks)}
        for number, weeks in enumerate(ANTENATAL_WEEKS, start=1)
    ]


def plan_resync(existing_visits: set[int], lmp: date, today: date | None = None) -> dict:
    """What to do with a mother's saved visits after her last-period date changes.

    - Every visit she already has moves to its new date. A visit she marked done stays done
      (the caller only changes the date), and an overdue one stays in the list as overdue,
      so a correction can never hide a visit she has not had.
    - A visit she does not have yet is added only if its new date is today or later. This is
      the same rule as at registration (visits already in the past are not invented).
    - Nothing is ever removed.

    Returns {"update": {visit_number: new_date}, "create": [{"visit", "week", "date"}]}.
    """
    today = today or date.today()
    update, create = {}, []
    for visit in antenatal_schedule(lmp):
        if visit["visit"] in existing_visits:
            update[visit["visit"]] = visit["date"]
        elif visit["date"] >= today:
            create.append(visit)
    return {"update": update, "create": create}
