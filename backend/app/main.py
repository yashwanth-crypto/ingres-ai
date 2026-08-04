"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat, health, tools

log = logging.getLogger(__name__)
settings = get_settings()


def _warm_model() -> None:
    """Load the local model into VRAM at startup, in the background.

    The first Ollama call costs ~45 seconds while weights load, and on demo day
    that lands on the opening question and looks like a hang. Doing it here
    means the first real question is fast. Failure is harmless - the model
    simply loads on first use, as before.
    """
    try:
        from app.services.llm_client import generate_text, provider

        if provider() != "ollama":
            return
        generate_text("Reply with OK.", "warmup", max_tokens=5)
        log.info("Local model warmed up.")
    except Exception as exc:  # never block startup on a warmup failure
        log.warning("Model warmup skipped: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm_model, daemon=True).start()
    yield


app = FastAPI(
    title="INGRES AI Assistant",
    description="Grounded answers about Punjab groundwater, from CGWB data.",
    version="0.1.0",
    lifespan=lifespan,
)

# Explicit origins only - never "*" (spec Section 10).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(tools.router)
app.include_router(chat.router)


@app.get("/", tags=["health"])
def root() -> dict:
    return {"service": "INGRES AI Assistant", "docs": "/docs"}
