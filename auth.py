"""Authentication building blocks. Plain Python (standard library only) so the
security-critical logic is easy to read and to test without a web server.

Design:
- A mother signs in with her phone number and a 6-digit PIN.
- PINs are never stored. We store a salted scrypt hash.
- After sign-in the app gets a random session token. Only the SHA-256 of the
  token is stored, so a stolen database does not reveal usable tokens.
- 5 wrong PINs lock that phone number for 15 minutes.
- Health-worker routes use a separate staff key from the MAMACARE_STAFF_KEY
  environment variable. If it is not set, staff routes are switched off.
"""

import base64
import hashlib
import hmac
import math
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

PIN_LENGTH = 6
MAX_FAILED_PINS = 5
LOCK_MINUTES = 15
SESSION_DAYS = 30

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def utcnow() -> datetime:
    """Naive UTC time (SQLite stores naive datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ phone ---

def normalise_phone(raw: str) -> str:
    """'+234 803 000 0000', '0803-000-0000' and '8030000000' -> '08030000000'.

    Raises ValueError if the result does not look like a phone number.
    """
    digits = re.sub(r"[\s\-().]", "", raw.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if not digits.isdigit():
        raise ValueError("Phone number can only contain digits, spaces, dashes and a leading +")
    if digits.startswith("234") and len(digits) == 13:
        digits = "0" + digits[3:]
    elif len(digits) == 10 and not digits.startswith("0"):
        digits = "0" + digits
    if not 7 <= len(digits) <= 15:
        raise ValueError("Enter a valid phone number, for example 0803 000 0000")
    return digits


# -------------------------------------------------------------------- PIN ---

def check_pin_strength(pin: str) -> str:
    if not re.fullmatch(rf"\d{{{PIN_LENGTH}}}", pin or ""):
        raise ValueError(f"PIN must be exactly {PIN_LENGTH} digits")
    if len(set(pin)) == 1:
        raise ValueError("PIN is too easy to guess. Do not repeat one digit")
    ascending = "01234567890123456789"
    if pin in ascending or pin in ascending[::-1]:
        raise ValueError("PIN is too easy to guess. Do not use a run of digits")
    return pin


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode(),
    )


def verify_pin(pin: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        actual = hashlib.scrypt(pin.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# A real hash to compare against when the phone number is unknown, so that
# "unknown number" and "wrong PIN" take the same time and give the same reply.
DUMMY_HASH = hash_pin("000000")


# ----------------------------------------------------------------- tokens ---

def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_expiry(now: datetime | None = None) -> datetime:
    return (now or utcnow()) + timedelta(days=SESSION_DAYS)


def bearer_token(authorization: str | None) -> str | None:
    """'Bearer abc' -> 'abc'; anything else -> None."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


# ---------------------------------------------------------------- lockout ---

def register_failed_pin(failed_count: int, now: datetime | None = None):
    """Return (new_failed_count, locked_until or None) after one wrong PIN."""
    failed_count += 1
    if failed_count >= MAX_FAILED_PINS:
        return 0, (now or utcnow()) + timedelta(minutes=LOCK_MINUTES)
    return failed_count, None


def minutes_left(locked_until: datetime, now: datetime | None = None) -> int:
    seconds = (locked_until - (now or utcnow())).total_seconds()
    return max(1, math.ceil(seconds / 60))


# ------------------------------------------------------------ staff access ---

def staff_key_matches(provided: str | None) -> bool:
    expected = os.getenv("MAMACARE_STAFF_KEY", "")
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


# ------------------------------------------------------------ rate limiting ---

class RateLimiter:
    """Allow at most `limit` calls per `window` seconds for each key (in memory,
    one server process). Good enough to stop casual abuse; use a shared store
    such as Redis if you run several server processes."""

    def __init__(self, limit: int, window: float, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.calls: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self.clock()
        q = self.calls[key]
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
