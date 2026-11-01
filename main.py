from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import auth
import models
from database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MamaCare")

# Per-IP limit on sign-in attempts (on top of the per-phone lockout).
login_limiter = auth.RateLimiter(limit=20, window=600)


# ------------------------------------------------------------------ schemas ---

def _lmp_must_be_plausible(v: date) -> date:
    today = date.today()
    if v > today:
        raise ValueError("LMP date cannot be in the future")
    if today - v > timedelta(days=294):
        raise ValueError("LMP date is more than 42 weeks ago; please check it")
    return v


class RegisterIn(BaseModel):
    name: str
    phone: str
    lmp_date: date
    pin: str

    @field_validator("name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        v = " ".join(v.split())
        if not 2 <= len(v) <= 100:
            raise ValueError("Enter your name (2 to 100 characters)")
        return v

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v: str) -> str:
        return auth.normalise_phone(v)

    @field_validator("lmp_date")
    @classmethod
    def lmp_ok(cls, v: date) -> date:
        return _lmp_must_be_plausible(v)

    @field_validator("pin")
    @classmethod
    def pin_ok(cls, v: str) -> str:
        return auth.check_pin_strength(v)


class LoginIn(BaseModel):
    phone: str
    pin: str

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v: str) -> str:
        return auth.normalise_phone(v)

    @field_validator("pin")
    @classmethod
    def pin_len(cls, v: str) -> str:
        if len(v) > 32:
            raise ValueError("PIN is too long")
        return v  # strength rules are for new PINs only; do not reveal them here


class MotherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    lmp_date: date
    due_date: date


class AuthOut(BaseModel):
    token: str
    mother: MotherOut


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    visit_number: int
    week: int
    due_date: date
    done: bool
    done_on: date | None


# -------------------------------------------------------------- pregnancy maths ---

def estimated_due_date(lmp: date) -> date:
    return lmp + timedelta(days=280)


ANTENATAL_WEEKS = [12, 20, 26, 30, 34, 36, 38, 40]


def antenatal_schedule(lmp: date) -> list:
    visits = []
    for number, weeks in enumerate(ANTENATAL_WEEKS, start=1):
        visits.append({
            "visit": number,
            "week": weeks,
            "date": lmp + timedelta(weeks=weeks),
        })
    return visits


# ------------------------------------------------------------------- access ---

def authorize(db: Session, mother_id: int, authorization: str | None, staff_key: str | None) -> None:
    """Allow health workers (staff key) or the mother herself. Anyone else is refused
    BEFORE we look the record up, so ids cannot be probed to see who is registered."""
    if auth.staff_key_matches(staff_key):
        return
    token = auth.bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    session = (
        db.query(models.AuthSession)
        .filter(models.AuthSession.token_hash == auth.hash_token(token))
        .first()
    )
    if session is None or session.expires_at <= auth.utcnow():
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
    if session.mother_id != mother_id:
        raise HTTPException(status_code=403, detail="You can only see your own records.")


def require_staff(x_staff_key: str | None = Header(default=None)) -> None:
    if not auth.staff_key_matches(x_staff_key):
        raise HTTPException(status_code=403, detail="Health worker access only.")


def _start_session(db: Session, mother_id: int) -> str:
    # tidy up this mother's expired sessions, then issue a new one
    db.query(models.AuthSession).filter(
        models.AuthSession.mother_id == mother_id,
        models.AuthSession.expires_at <= auth.utcnow(),
    ).delete()
    token = auth.new_token()
    db.add(models.AuthSession(
        mother_id=mother_id,
        token_hash=auth.hash_token(token),
        expires_at=auth.session_expiry(),
    ))
    return token


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ------------------------------------------------------------------- pages ---

WEB_DIR = Path(__file__).parent / "web"


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health():
    return {"message": "MamaCare is running"}


# Public: these take a date only and handle no personal data.
@app.get("/due-date")
def due_date(lmp: date):
    return {"lmp": lmp, "due_date": estimated_due_date(lmp)}


@app.get("/antenatal-schedule")
def antenatal(lmp: date):
    return antenatal_schedule(lmp)


# --------------------------------------------------------------------- auth ---

@app.post("/auth/register", response_model=AuthOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    taken = HTTPException(status_code=409, detail="This phone number is already registered. Sign in instead.")
    if db.query(models.Credential).filter(models.Credential.phone_key == data.phone).first():
        raise taken
    try:
        mother = models.Mother(
            name=data.name,
            phone=data.phone,
            lmp_date=data.lmp_date,
            due_date=estimated_due_date(data.lmp_date),
        )
        db.add(mother)
        db.flush()
        db.add(models.Credential(mother_id=mother.id, phone_key=data.phone, pin_hash=auth.hash_pin(data.pin)))
        for visit in antenatal_schedule(data.lmp_date):
            if visit["date"] >= date.today():
                db.add(models.Appointment(
                    mother_id=mother.id,
                    visit_number=visit["visit"],
                    week=visit["week"],
                    due_date=visit["date"],
                ))
        token = _start_session(db, mother.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise taken
    db.refresh(mother)
    return {"token": token, "mother": mother}


@app.post("/auth/login", response_model=AuthOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    if not login_limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait a few minutes and try again.")

    wrong = HTTPException(status_code=401, detail="Wrong phone number or PIN.")
    cred = db.query(models.Credential).filter(models.Credential.phone_key == data.phone).first()
    if cred is None:
        auth.verify_pin(data.pin, auth.DUMMY_HASH)  # same time and reply as a wrong PIN
        raise wrong

    now = auth.utcnow()
    if cred.locked_until and cred.locked_until > now:
        raise HTTPException(
            status_code=429,
            detail=f"Too many wrong PINs. Try again in {auth.minutes_left(cred.locked_until, now)} minutes.",
        )

    if not auth.verify_pin(data.pin, cred.pin_hash):
        cred.failed_count, cred.locked_until = auth.register_failed_pin(cred.failed_count, now)
        db.commit()
        raise wrong

    cred.failed_count, cred.locked_until = 0, None
    token = _start_session(db, cred.mother_id)
    db.commit()
    return {"token": token, "mother": db.get(models.Mother, cred.mother_id)}


@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    token = auth.bearer_token(authorization)
    if token:
        db.query(models.AuthSession).filter(models.AuthSession.token_hash == auth.hash_token(token)).delete()
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ mothers ---

@app.get("/mothers", response_model=list[MotherOut], dependencies=[Depends(require_staff)])
def list_mothers(db: Session = Depends(get_db)):
    """Health workers only: returns everyone's name and phone number."""
    return db.query(models.Mother).all()


@app.get("/mothers/{mother_id}", response_model=MotherOut)
def get_mother(
    mother_id: int,
    authorization: str | None = Header(default=None),
    x_staff_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    authorize(db, mother_id, authorization, x_staff_key)
    mother = db.get(models.Mother, mother_id)
    if mother is None:
        raise HTTPException(status_code=404, detail="Mother not found")
    return mother


@app.delete("/mothers/{mother_id}")
def delete_mother(
    mother_id: int,
    authorization: str | None = Header(default=None),
    x_staff_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Erase a mother's profile, visits and sign-in details."""
    authorize(db, mother_id, authorization, x_staff_key)
    mother = db.get(models.Mother, mother_id)
    if mother is None:
        raise HTTPException(status_code=404, detail="Mother not found")
    for model in (models.AuthSession, models.Credential, models.Appointment):
        db.query(model).filter(model.mother_id == mother_id).delete()
    db.delete(mother)
    db.commit()
    return {"deleted": True}


@app.get("/mothers/{mother_id}/schedule")
def mother_schedule(
    mother_id: int,
    authorization: str | None = Header(default=None),
    x_staff_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    authorize(db, mother_id, authorization, x_staff_key)
    mother = db.get(models.Mother, mother_id)
    if mother is None:
        raise HTTPException(status_code=404, detail="Mother not found")
    return antenatal_schedule(mother.lmp_date)


@app.get("/mothers/{mother_id}/appointments", response_model=list[AppointmentOut])
def mother_appointments(
    mother_id: int,
    authorization: str | None = Header(default=None),
    x_staff_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    authorize(db, mother_id, authorization, x_staff_key)
    mother = db.get(models.Mother, mother_id)
    if mother is None:
        raise HTTPException(status_code=404, detail="Mother not found")
    return (
        db.query(models.Appointment)
        .filter(models.Appointment.mother_id == mother_id)
        .order_by(models.Appointment.due_date)
        .all()
    )


@app.post("/appointments/{appointment_id}/done", response_model=AppointmentOut)
def mark_done(
    appointment_id: int,
    authorization: str | None = Header(default=None),
    x_staff_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    appointment = db.get(models.Appointment, appointment_id)
    if appointment is None:
        # Require sign-in even for a missing id, so ids cannot be probed anonymously.
        authorize(db, -1, authorization, x_staff_key)
        raise HTTPException(status_code=404, detail="Appointment not found")
    authorize(db, appointment.mother_id, authorization, x_staff_key)
    if not appointment.done:
        appointment.done = True
        appointment.done_on = date.today()
        db.commit()
        db.refresh(appointment)
    return appointment


@app.get("/missed", dependencies=[Depends(require_staff)])
def missed_visits(as_of: date | None = None, db: Session = Depends(get_db)):
    """Health workers only: overdue visits with the mother's name and phone number."""
    today = as_of or date.today()
    rows = (
        db.query(models.Appointment, models.Mother)
        .join(models.Mother, models.Mother.id == models.Appointment.mother_id)
        .filter(models.Appointment.done.is_(False))
        .filter(models.Appointment.due_date < today)
        .order_by(models.Appointment.due_date)
        .all()
    )
    return [
        {
            "appointment_id": a.id,
            "mother_id": m.id,
            "mother": m.name,
            "phone": m.phone,
            "visit_number": a.visit_number,
            "week": a.week,
            "due_date": a.due_date,
            "days_overdue": (today - a.due_date).days,
        }
        for a, m in rows
    ]


from ai_routes import router as ai_router  # noqa: E402

app.include_router(ai_router)
