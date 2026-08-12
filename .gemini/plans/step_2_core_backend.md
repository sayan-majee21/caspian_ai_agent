# Step 2: Core Backend Setup Implementation Plan

## Overview
This step establishes the foundational backend infrastructure for the TalentCaspian application. We will set up the project dependencies, configure the environment, establish a robust connection pool for PostgreSQL using `asyncpg`, and initialize the FastAPI application with standard middleware and health check endpoints.

## 1. Dependencies & Configuration

### `requirements.txt`
Create or update `requirements.txt` with the following core dependencies:
```text
fastapi>=0.110.0
uvicorn>=0.29.0
caspian-sdk>=0.1.0
asyncpg>=0.29.0
pytest>=8.1.1
pytest-asyncio>=0.23.6
python-dotenv>=1.0.1
google-generativeai>=0.4.1
httpx>=0.27.0
pydantic>=2.6.4
pydantic-settings>=2.2.1
```

### `.env.example`
Define the required environment variables:
```env
# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/talentcaspian

# API Configuration
PORT=5001
CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"]

# Caspian SDK Configuration
CASPIAN_API_KEY=your_caspian_api_key_here

# Google Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here

# Security & Webhooks
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret_here
GITHUB_TOKEN=your_github_pat_here
ADMIN_API_KEY=your_admin_api_key_here
```

## 2. Database Layer (`database/db.py`)

Implement the database connection management using `asyncpg`:

*   **Connection Pool:** Create a global `asyncpg.Pool` object.
*   **Lifespan Management:** Define functions to initialize the pool on startup and close it on shutdown. These will be integrated into the FastAPI lifespan.
*   **Dependency Injection:** Implement a `get_db_connection` asynchronous generator yielding a connection from the pool, to be used with FastAPI's `Depends`.

```python
import os
import asyncpg
from typing import AsyncGenerator

DB_POOL: asyncpg.Pool | None = None

async def init_db_pool() -> None:
    global DB_POOL
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/talentcaspian")
    DB_POOL = await asyncpg.create_pool(dsn=database_url, min_size=5, max_size=20)

async def close_db_pool() -> None:
    global DB_POOL
    if DB_POOL:
        await DB_POOL.close()

async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    if DB_POOL is None:
        raise RuntimeError("Database pool is not initialized")
    async with DB_POOL.acquire() as connection:
        yield connection

def is_pool_ready() -> bool:
    return DB_POOL is not None
```

## 3. FastAPI Core Application (`main.py`)

Set up the main FastAPI application:

*   **App Instantiation:** Initialize FastAPI with title, description, and version.
*   **Lifespan Context Manager:** Use `@asynccontextmanager` to tie `init_db_pool` and `close_db_pool` to the application's lifecycle.
*   **Middleware:** Add `CORSMiddleware` using origins loaded from environment variables.
*   **Endpoints:** Implement `GET /` and `GET /health` endpoints.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import json
import os
from typing import Any

from database.db import init_db_pool, close_db_pool, is_pool_ready

@asynccontextmanager
async def lifespan(app: FastAPI):
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
    # NOTE: is_pool_ready() reads the DB_POOL module global at call time.
    # Importing DB_POOL directly (the old approach) captures a stale None
    # reference taken at import time, before lifespan startup runs.
    db_status = "connected" if is_pool_ready() else "disconnected"
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status
    }
```

## 4. Testing Infrastructure (`tests/test_02_core_backend.py`)

Create automated tests using `pytest` and `pytest-asyncio` to verify the backend setup:

*   **Test Setup:** Configure an async test client using `httpx.AsyncClient` connected to the FastAPI app via `ASGITransport`.
*   **Health Check Test:** Verify that `GET /health` returns a 200 OK status and the expected JSON structure, including `"database": "connected"`.
*   **Database Pool Test:** Verify that the database pool initializes correctly and dependencies can be injected.

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.mark.asyncio
async def test_health_check():
    # httpx >= 0.27 removed the `app=` shortcut on AsyncClient.
    # Use ASGITransport explicitly, or this raises TypeError at collection time.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["database"] in ["connected", "disconnected"]  # Depending on test db setup
```

## Execution Steps
1. Create `requirements.txt` and `.env.example`.
2. Install dependencies: `pip install -r requirements.txt`.
3. Implement `database/db.py`.
4. Implement `main.py`.
5. Implement `tests/test_02_core_backend.py`.
6. Run tests: `pytest tests/test_02_core_backend.py`.
