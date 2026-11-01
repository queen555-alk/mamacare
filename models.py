from datetime import date, datetime

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


class Credential(Base):
    """Sign-in details live in their own table so the existing `mothers` table
    does not need to change (create_all adds new tables but never alters old ones)."""

    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    mother_id: Mapped[int] = mapped_column(ForeignKey("mothers.id"), unique=True)
    phone_key: Mapped[str] = mapped_column(unique=True, index=True)
    pin_hash: Mapped[str]
    failed_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(default=None)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    mother_id: Mapped[int] = mapped_column(ForeignKey("mothers.id"), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True, index=True)
    expires_at: Mapped[datetime]
