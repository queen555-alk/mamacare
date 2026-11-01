import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import auth


@pytest.mark.parametrize("raw, expected", [
    ("0803 000 0000", "08030000000"),
    ("+234 803 000 0000", "08030000000"),
    ("2348030000000", "08030000000"),
    ("8030000000", "08030000000"),
    ("(0803) 000-0000", "08030000000"),
])
def test_phone_numbers_are_normalised_to_one_form(raw, expected):
    assert auth.normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12", "0803-abc-0000", "1" * 20])
def test_bad_phone_numbers_are_rejected(raw):
    with pytest.raises(ValueError):
        auth.normalise_phone(raw)


@pytest.mark.parametrize("pin", ["", "12345", "1234567", "12ab56", "000000", "111111", "123456", "654321", "012345"])
def test_weak_or_malformed_pins_are_rejected(pin):
    with pytest.raises(ValueError):
        auth.check_pin_strength(pin)


def test_reasonable_pin_is_accepted():
    assert auth.check_pin_strength("493021") == "493021"


def test_pin_hash_verifies_and_is_salted():
    h1, h2 = auth.hash_pin("493021"), auth.hash_pin("493021")
    assert h1 != h2                      # different salt each time
    assert "493021" not in h1            # never stored in the clear
    assert auth.verify_pin("493021", h1)
    assert not auth.verify_pin("493022", h1)


def test_garbage_hash_does_not_crash_or_verify():
    assert not auth.verify_pin("493021", "not-a-hash")
    assert not auth.verify_pin("493021", "md5$1$2$3$4$5")


def test_tokens_are_random_and_stored_hashed():
    a, b = auth.new_token(), auth.new_token()
    assert a != b and len(a) >= 40
    assert auth.hash_token(a) != a
    assert auth.hash_token(a) == auth.hash_token(a)


@pytest.mark.parametrize("header, expected", [
    ("Bearer abc123", "abc123"), ("bearer abc123", "abc123"),
    (None, None), ("", None), ("Bearer", None), ("Basic abc", None), ("abc123", None),
])
def test_bearer_parsing(header, expected):
    assert auth.bearer_token(header) == expected


def test_five_wrong_pins_lock_the_account_for_15_minutes():
    now = auth.utcnow()
    count, locked = 0, None
    for _ in range(4):
        count, locked = auth.register_failed_pin(count, now)
        assert locked is None
    count, locked = auth.register_failed_pin(count, now)
    assert locked == now + timedelta(minutes=15)
    assert count == 0


def test_minutes_left_never_shows_zero():
    now = auth.utcnow()
    assert auth.minutes_left(now + timedelta(seconds=5), now) == 1
    assert auth.minutes_left(now + timedelta(minutes=15), now) == 15
    assert auth.minutes_left(now + timedelta(minutes=14, seconds=1), now) == 15
    assert auth.minutes_left(now - timedelta(minutes=1), now) == 1


def test_staff_key_is_off_unless_configured(monkeypatch):
    monkeypatch.delenv("MAMACARE_STAFF_KEY", raising=False)
    assert not auth.staff_key_matches("anything")
    assert not auth.staff_key_matches(None)
    monkeypatch.setenv("MAMACARE_STAFF_KEY", "s3cret-key")
    assert auth.staff_key_matches("s3cret-key")
    assert not auth.staff_key_matches("wrong")
    assert not auth.staff_key_matches(None)
    assert not auth.staff_key_matches("")


def test_rate_limiter_blocks_then_recovers():
    clock = {"t": 0.0}
    rl = auth.RateLimiter(limit=3, window=60, clock=lambda: clock["t"])
    assert [rl.allow("ip") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("other-ip")          # separate key
    clock["t"] = 61
    assert rl.allow("ip")                # window has passed
