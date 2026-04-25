"""
flowstate-ai FastAPI application.

Run with:
    python run.py
    — or —
    uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_db, connect_db
from app.routers import auth, calendar, preferences, schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open MongoDB connection on startup; close it on shutdown."""
    logger.info("Connecting to MongoDB...")
    await connect_db()
    logger.info("MongoDB connected.")
    yield
    logger.info("Closing MongoDB connection...")
    await close_db()
    logger.info("MongoDB connection closed.")


settings = get_settings()

app = FastAPI(
    title="flowstate-ai API",
    description=(
        "Backend for flowstate-ai — converts todo lists into Google Calendar changes "
        "using Gemini 2.5 Pro."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Allow localhost on any port for development, plus the configured frontend origin.
_allowed_origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    settings.frontend_origin,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(calendar.router)
app.include_router(schedule.router)
app.include_router(preferences.router)


@app.get("/", tags=["health"])
async def health_check():
    """Simple health-check endpoint."""
    return {"status": "ok", "service": "flowstate-ai"}
