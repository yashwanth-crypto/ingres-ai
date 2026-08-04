"""POST /chat - the main endpoint (spec Section 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.orchestrator import handle_chat
from app.database import get_db

router = APIRouter(tags=["chat"])


class Turn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list)


@router.post("/chat")
def chat(body: ChatRequest, db: Session = Depends(get_db)) -> dict:
    return handle_chat(
        db, body.message, [t.model_dump() for t in body.history]
    )
