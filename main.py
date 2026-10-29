from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

import models
from database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MamaCare")


class MotherCreate(BaseModel):
    name: str
    phone: str
    lmp_date: date

    @field_validator("lmp_date")
    @classmethod
    def lmp_must_be_plausible(cls, v: date) -> date:
        today = date.today()
        if v > today:
            raise ValueError("LMP date cannot be in the future")
        if today - v > timedelta(days=294):
            raise ValueError("LMP date is more than 42 weeks ago; please check it")
        return v


class MotherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    lmp_date: date
    due_date: date


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    visit_number: int
    week: int
    due_date: date
    done: bool
    done_on: date | None


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


@app.get("/")
def home():
    return {"message": "MamaCare is running"}


@app.get("/due-date")
def due_date(lmp: date):
    return {"lmp": lmp, "due_date": estimated_due_date(lmp)}


@app.get("/antenatal-schedule")
def antenatal(lmp: date):
    return antenatal_schedule(lmp)


@app.post("/mothers", response_model=MotherOut)
def register_mother(data: MotherCreate, db: Session = Depends(get_db)):
    mother = models.Mother(
        name=data.name,
        phone=data.phone,
        lmp_date=data.lmp_date,
        due_date=estimated_due_date(data.lmp_date),
    )
    db.add(mother)
    db.flush()
    for visit in antenatal_schedule(data.lmp_date):
        if visit["date"] >= date.today():
            db.add(models.Appointment(
                mother_id=mother.id,
                visit_number=visit["visit"],
                week=visit["week"],
                due_date=visit["date"],
            ))
    db.commit()
    db.refresh(mother)
    return mother


@app.get("/mothers", response_model=list[MotherOut])
def list_mothers(db: Session = Depends(get_db)):
    return db.query(models.Mother).all()


@app.get("/mothers/{mother_id}/schedule")
def mother_schedule(mother_id: int, db: Session = Depends(get_db)):
    mother = db.get(models.Mother, mother_id)
    if mother is None:
        raise HTTPException(status_code=404, detail="Mother not found")
    return antenatal_schedule(mother.lmp_date)


@app.get("/mothers/{mother_id}/appointments", response_model=list[AppointmentOut])
def mother_appointments(mother_id: int, db: Session = Depends(get_db)):
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
def mark_done(appointment_id: int, db: Session = Depends(get_db)):
    appointment = db.get(models.Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appointment.done = True
    appointment.done_on = date.today()
    db.commit()
    db.refresh(appointment)
    return appointment


@app.get("/missed")
def missed_visits(as_of: date | None = None, db: Session = Depends(get_db)):
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


from ai_routes import router as ai_router
app.include_router(ai_router)
