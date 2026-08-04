"""Health check (spec Section 6)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.database import engine
from app.schemas import Health
from app.services import llm_client

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def health() -> Health:
    db_connected = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False

    # Never spends tokens: for Anthropic this only checks the key is present,
    # for Ollama it pings the local version endpoint.
    return Health(
        status="ok" if db_connected else "degraded",
        db_connected=db_connected,
        llm_reachable=llm_client.reachable(),
        llm_backend=llm_client.describe(),
    )
