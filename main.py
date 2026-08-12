"""TalentCaspian FastAPI Core Application."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import init_db_pool, close_db_pool, is_pool_ready


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application startup and shutdown."""
    # Startup
    await init_db_pool()
    yield
    # Shutdown
    await close_db_pool()


app = FastAPI(
    title="TalentCaspian API",
    description="Backend API for TalentCaspian portfolio tracker and recruitment matcher.",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS (supports CORS_ORIGINS array or FRONTEND_URL string)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
origins_str = os.getenv("CORS_ORIGINS", f'["{frontend_url}"]')
try:
    origins = json.loads(origins_str)
    if frontend_url not in origins:
        origins.append(frontend_url)
except json.JSONDecodeError:
    origins = [frontend_url, "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """Health check endpoint to report API status and DB connectivity.

    Returns:
        dict[str, Any]: Application health status.
    """
    db_status = "connected" if is_pool_ready() else "disconnected"
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status
    }
