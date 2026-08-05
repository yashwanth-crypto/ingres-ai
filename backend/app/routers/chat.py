"""POST /chat - the main endpoint (spec Section 6), plus its streaming twin."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.orchestrator import handle_chat, run_chat
from app.database import SessionLocal, get_db

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


@router.post("/chat/stream")
def chat_stream(body: ChatRequest) -> StreamingResponse:
    """The same pipeline, reporting each step as it reaches it.

    Server-sent events: one `data:` line per stage, ending with the finished
    answer. Answering takes 3 to 15 seconds, and none of the work was visible
    for any of it.

    The session is opened inside the generator rather than injected. A
    dependency is torn down when the *handler* returns, which for a streaming
    response is before the body has been produced - the session would be closed
    under the pipeline while it was still querying.
    """
    history = [t.model_dump() for t in body.history]

    def events() -> Iterator[str]:
        db = SessionLocal()
        try:
            for event in run_chat(db, body.message, history):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx and friends buffer streamed responses by default, which
            # would hold every stage back and deliver them all at the end -
            # exactly the silence this endpoint exists to remove.
            "X-Accel-Buffering": "no",
        },
    )
