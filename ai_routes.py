"""Web endpoints for the health-education assistant.

Added to the main app with:
    from ai_routes import router as ai_router
    app.include_router(ai_router)

Privacy: questions can contain personal health details, so they are NOT logged
or stored anywhere by this module.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from assistant import Assistant

router = APIRouter(prefix="/assistant", tags=["assistant"])

_assistant = Assistant.default()


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class SourceOut(BaseModel):
    id: str
    title: str
    source: str


class AskOut(BaseModel):
    kind: str  # answer | emergency | crisis | refused | no_source
    answer: str
    sources: list[SourceOut]


@router.post("/ask", response_model=AskOut)
def ask(body: AskIn):
    """Ask a health-education question. Answers come only from the guidance notes."""
    return _assistant.ask(body.question)


@router.get("/sources", response_model=list[SourceOut])
def list_sources():
    """The guidance notes the assistant is allowed to use."""
    return _assistant.sources()
