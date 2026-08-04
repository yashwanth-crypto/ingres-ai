"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat, health, tools

settings = get_settings()

app = FastAPI(
    title="INGRES AI Assistant",
    description="Grounded answers about Punjab groundwater, from CGWB data.",
    version="0.1.0",
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
