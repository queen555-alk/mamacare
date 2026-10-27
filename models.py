from datetime import date

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Mother(Base):
    __tablename__ = "mothers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    phone: Mapped[str]
    lmp_date: Mapped[date]
    due_date: Mapped[date]


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    mother_id: Mapped[int] = mapped_column(ForeignKey("mothers.id"))
    visit_number: Mapped[int]
    week: Mapped[int]
    due_date: Mapped[date]
    done: Mapped[bool] = mapped_column(default=False)
    done_on: Mapped[date | None] = mapped_column(default=None)
