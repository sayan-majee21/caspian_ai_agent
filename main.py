"""TalentCaspian FastAPI Core Application."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import close_db_pool, init_db_pool, is_pool_ready
from routers.admin import router as admin_router
from routers.public import router as public_router
from routers.recruiters import router as recruiter_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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

# Include routers
app.include_router(public_router)
app.include_router(recruiter_router)
app.include_router(admin_router)

# Configure CORS (supports JSON array or comma-separated origins)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
origins_env = os.getenv("CORS_ORIGINS")

origins: list[str] = []
if origins_env:
    try:
        parsed = json.loads(origins_env)
        if isinstance(parsed, list):
            origins = [str(o).strip() for o in parsed]
        elif isinstance(parsed, str):
            origins = [o.strip() for o in parsed.split(",") if o.strip()]
    except json.JSONDecodeError:
        origins = [o.strip() for o in origins_env.split(",") if o.strip()]

if frontend_url and frontend_url not in origins and "*" not in origins:
    origins.append(frontend_url)

if not origins:
    origins = [frontend_url, "http://localhost:5173"]

# Credentials cannot be allowed when origins contains wildcard "*"
allow_credentials = "*" not in origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
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
        "database": db_status,
    }
