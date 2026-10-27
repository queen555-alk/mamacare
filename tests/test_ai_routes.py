import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_routes import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_ask_returns_answer_with_sources():
    r = client.post("/assistant/ask", json={"question": "How many antenatal visits should I have?"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "answer"
    assert body["sources"][0]["id"] == "antenatal_schedule"


def test_ask_emergency():
    r = client.post("/assistant/ask", json={"question": "I am bleeding heavily"})
    assert r.json()["kind"] == "emergency"


def test_too_short_question_rejected():
    assert client.post("/assistant/ask", json={"question": "hi"}).status_code == 422


def test_sources_listed():
    r = client.get("/assistant/sources")
    assert r.status_code == 200
    assert len(r.json()) >= 15
