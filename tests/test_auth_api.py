"""End-to-end tests of sign-in and access control through the real FastAPI app.

Skipped automatically if fastapi / sqlalchemy / httpx are not installed.
Each test gets a fresh in-memory database.
"""

import sys
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import ai_routes  # noqa: E402
import auth  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from database import Base, get_db  # noqa: E402

STAFF = {"X-Staff-Key": "staff-secret"}


@pytest.fixture()
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture()
def client(Session, monkeypatch):
    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override
    main.login_limiter.calls.clear()
    ai_routes._limiter.calls.clear()
    monkeypatch.setenv("MAMACARE_STAFF_KEY", "staff-secret")
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    ai_routes._limiter.calls.clear()


def lmp_weeks_ago(weeks=14):
    return (date.today() - timedelta(weeks=weeks)).isoformat()


def register(client, phone="0803 000 0000", pin="493021", name="Amaka Obi"):
    return client.post("/auth/register", json={"name": name, "phone": phone, "lmp_date": lmp_weeks_ago(), "pin": pin})


def bearer(resp):
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# ------------------------------------------------------------ registration ---

def test_register_returns_token_and_mother_with_normalised_phone(client):
    r = register(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["mother"]["phone"] == "08030000000"
    assert "pin" not in body["mother"]


def test_register_stores_no_plain_pin_or_token(client, Session):
    r = register(client, pin="493021")
    db = Session()
    cred = db.query(models.Credential).one()
    assert "493021" not in cred.pin_hash
    stored = db.query(models.AuthSession).one()
    assert stored.token_hash != r.json()["token"]


@pytest.mark.parametrize("pin", ["123456", "000000", "12345", "abcdef"])
def test_weak_pin_rejected(client, pin):
    assert register(client, pin=pin).status_code == 422


def test_same_phone_in_another_format_is_a_duplicate(client):
    assert register(client, phone="0803 000 0000").status_code == 200
    assert register(client, phone="+234 803 000 0000", name="Someone Else").status_code == 409


def test_old_open_registration_route_is_gone(client):
    r = client.post("/mothers", json={"name": "X Y", "phone": "0803", "lmp_date": lmp_weeks_ago()})
    assert r.status_code in (404, 405)


# ----------------------------------------------------------------- sign-in ---

def test_login_works_with_any_phone_format(client):
    register(client)
    r = client.post("/auth/login", json={"phone": "+2348030000000", "pin": "493021"})
    assert r.status_code == 200 and r.json()["token"]


def test_wrong_pin_and_unknown_phone_look_the_same(client):
    register(client)
    wrong_pin = client.post("/auth/login", json={"phone": "08030000000", "pin": "111222"})
    unknown = client.post("/auth/login", json={"phone": "08099999999", "pin": "111222"})
    assert wrong_pin.status_code == unknown.status_code == 401
    assert wrong_pin.json() == unknown.json()


def test_five_wrong_pins_lock_the_account_even_for_the_right_pin(client):
    register(client)
    for _ in range(5):
        assert client.post("/auth/login", json={"phone": "08030000000", "pin": "111222"}).status_code == 401
    locked = client.post("/auth/login", json={"phone": "08030000000", "pin": "493021"})
    assert locked.status_code == 429
    assert "minutes" in locked.json()["detail"]


def test_successful_login_resets_the_failure_count(client, Session):
    register(client)
    for _ in range(3):
        client.post("/auth/login", json={"phone": "08030000000", "pin": "111222"})
    assert client.post("/auth/login", json={"phone": "08030000000", "pin": "493021"}).status_code == 200
    assert Session().query(models.Credential).one().failed_count == 0


def test_login_is_rate_limited_per_ip(client):
    for _ in range(20):
        client.post("/auth/login", json={"phone": "08099999999", "pin": "111222"})
    assert client.post("/auth/login", json={"phone": "08099999999", "pin": "111222"}).status_code == 429


# ------------------------------------------------------------ access control ---

def test_records_need_a_token(client):
    mother_id = register(client).json()["mother"]["id"]
    for path in (f"/mothers/{mother_id}", f"/mothers/{mother_id}/appointments", f"/mothers/{mother_id}/schedule"):
        assert client.get(path).status_code == 401, path
    assert client.get(f"/mothers/{mother_id}", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_a_mother_can_read_her_own_records(client):
    r = register(client)
    mid, h = r.json()["mother"]["id"], bearer(r)
    assert client.get(f"/mothers/{mid}", headers=h).status_code == 200
    appts = client.get(f"/mothers/{mid}/appointments", headers=h)
    assert appts.status_code == 200 and len(appts.json()) >= 1
    assert client.get(f"/mothers/{mid}/schedule", headers=h).status_code == 200


def test_a_mother_cannot_read_or_change_another_mothers_records(client):
    a = register(client, phone="0803 000 0001", name="Mother A")
    b = register(client, phone="0803 000 0002", name="Mother B")
    a_id, b_id = a.json()["mother"]["id"], b.json()["mother"]["id"]
    assert client.get(f"/mothers/{b_id}", headers=bearer(a)).status_code == 403
    assert client.get(f"/mothers/{b_id}/appointments", headers=bearer(a)).status_code == 403
    b_appt = client.get(f"/mothers/{b_id}/appointments", headers=bearer(b)).json()[0]["id"]
    assert client.post(f"/appointments/{b_appt}/done", headers=bearer(a)).status_code == 403
    assert client.delete(f"/mothers/{b_id}", headers=bearer(a)).status_code == 403
    assert client.get(f"/mothers/{a_id}", headers=bearer(a)).status_code == 200


def test_list_and_missed_routes_are_staff_only(client):
    r = register(client)
    for path in ("/mothers", "/missed"):
        assert client.get(path).status_code == 403
        assert client.get(path, headers=bearer(r)).status_code == 403
        assert client.get(path, headers={"X-Staff-Key": "wrong"}).status_code == 403
        assert client.get(path, headers=STAFF).status_code == 200


def test_staff_routes_are_off_when_no_staff_key_is_configured(client, monkeypatch):
    monkeypatch.delenv("MAMACARE_STAFF_KEY", raising=False)
    assert client.get("/mothers", headers=STAFF).status_code == 403


def test_staff_can_read_a_mothers_records(client):
    r = register(client)
    mid = r.json()["mother"]["id"]
    assert client.get(f"/mothers/{mid}", headers=STAFF).status_code == 200


def test_expired_session_is_refused(client, Session):
    r = register(client)
    mid = r.json()["mother"]["id"]
    db = Session()
    db.query(models.AuthSession).update({"expires_at": auth.utcnow() - timedelta(minutes=1)})
    db.commit()
    assert client.get(f"/mothers/{mid}", headers=bearer(r)).status_code == 401


def test_logout_ends_the_session(client):
    r = register(client)
    mid = r.json()["mother"]["id"]
    assert client.post("/auth/logout", headers=bearer(r)).status_code == 200
    assert client.get(f"/mothers/{mid}", headers=bearer(r)).status_code == 401


# -------------------------------------------------------------- visits, erase ---

def test_mark_done_records_the_date_and_is_idempotent(client):
    r = register(client)
    mid, h = r.json()["mother"]["id"], bearer(r)
    appt = client.get(f"/mothers/{mid}/appointments", headers=h).json()[0]["id"]
    first = client.post(f"/appointments/{appt}/done", headers=h).json()
    assert first["done"] is True and first["done_on"] == date.today().isoformat()
    assert client.post(f"/appointments/{appt}/done", headers=h).json() == first


def test_missing_appointment_needs_sign_in_then_404(client):
    assert client.post("/appointments/9999/done").status_code == 401


def test_a_mother_can_erase_her_data(client, Session):
    r = register(client)
    mid, h = r.json()["mother"]["id"], bearer(r)
    assert client.delete(f"/mothers/{mid}", headers=h).json() == {"deleted": True}
    db = Session()
    for model in (models.Mother, models.Credential, models.Appointment, models.AuthSession):
        assert db.query(model).count() == 0, model.__name__
    assert client.post("/auth/login", json={"phone": "08030000000", "pin": "493021"}).status_code == 401


# ------------------------------------------------------------------ public ---

def test_calculator_routes_stay_public(client):
    lmp = lmp_weeks_ago()
    assert client.get(f"/due-date?lmp={lmp}").status_code == 200
    assert len(client.get(f"/antenatal-schedule?lmp={lmp}").json()) == 8


def test_home_page_and_health_check(client):
    assert client.get("/health").json() == {"message": "MamaCare is running"}
    page = client.get("/")
    assert page.status_code == 200 and "MamaCare" in page.text


# ------------------------------------------------- assistant rate limiting ---

def test_assistant_is_rate_limited_but_emergencies_never_are(client, monkeypatch):
    monkeypatch.setattr(ai_routes, "_limiter", auth.RateLimiter(limit=3, window=60))
    ok = [client.post("/assistant/ask", json={"question": "How many antenatal visits should I have?"}).status_code for _ in range(4)]
    assert ok == [200, 200, 200, 429]
    for _ in range(10):
        r = client.post("/assistant/ask", json={"question": "I am bleeding heavily"})
        assert r.status_code == 200 and r.json()["kind"] == "emergency"
    r = client.post("/assistant/ask", json={"question": "I want to end my life"})
    assert r.status_code == 200 and r.json()["kind"] == "crisis"
