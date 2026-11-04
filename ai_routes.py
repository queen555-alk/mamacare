"""Web endpoints for the health-education assistant.

Added to the main app with:
    from ai_routes import router as ai_router
    app.include_router(ai_router)

Privacy: questions can contain personal health details, so they are NOT logged
or stored anywhere by this module.
"""

import os

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

import auth
from assistant import Assistant

router = APIRouter(prefix="/assistant", tags=["assistant"])

_assistant = Assistant.default()

# Stops one client from running up the language-model bill. Over the limit the assistant
# keeps working but skips the model (see ask below).
_limiter = auth.RateLimiter(limit=int(os.getenv("ASSISTANT_RATE_LIMIT", "30")), window=60)


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class SourceOut(BaseModel):
    id: str
    title: str
    source: str


class AskOut(BaseModel):
    kind: str  # answer | emergency | crisis | refused | concern | no_source
    answer: str
    sources: list[SourceOut]


@router.post("/ask", response_model=AskOut)
def ask(body: AskIn, request: Request):
    """Ask a health-education question. Answers come only from the guidance notes."""
    ip = request.client.host if request.client else "unknown"
    # Over the limit we still answer, but without any language-model step. A person is
    # never refused help, and the keyword safety rules always run.
    return _assistant.ask(body.question, use_ai=_limiter.allow(ip))


@router.get("/sources", response_model=list[SourceOut])
def list_sources():
    """The guidance notes the assistant is allowed to use."""
    return _assistant.sources()


def get_assistant() -> Assistant:
    return _assistant


def allow_ai(key: str) -> bool:
    """True if this caller may still use the language model in this minute."""
    return _limiter.allow(key)
