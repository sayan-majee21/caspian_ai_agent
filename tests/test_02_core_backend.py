"""Unit and integration tests for Step 2: Core Backend Setup."""

from datetime import datetime
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database.db as db_module
from main import app, lifespan


@pytest.fixture(autouse=True)
def reset_db_pool():
    """Fixture to ensure DB_POOL is reset to None after each test."""
    db_module.DB_POOL = None
    yield
    db_module.DB_POOL = None


# ---------------------------------------------------------------------------
# 1. Endpoint Status Code & Schema Validation (GET /health and GET /)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_disconnected_schema():
    """Test GET /health status code 200 and schema validation when DB is disconnected."""
    db_module.DB_POOL = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["status"] == "ok"
    assert data["database"] == "disconnected"
    assert "timestamp" in data
    ts = datetime.fromisoformat(data["timestamp"])
    assert ts is not None


@pytest.mark.asyncio
async def test_health_check_connected_schema():
    """Test GET /health status code 200 and schema validation when DB is connected."""
    db_module.DB_POOL = MagicMock()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "timestamp" in data
    ts = datetime.fromisoformat(data["timestamp"])
    assert ts is not None


@pytest.mark.asyncio
async def test_root_endpoint_disconnected_schema():
    """Test GET / status code 200 and schema validation when DB is disconnected."""
    db_module.DB_POOL = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["status"] == "ok"
    assert data["database"] == "disconnected"
    assert "timestamp" in data
    ts = datetime.fromisoformat(data["timestamp"])
    assert ts is not None


@pytest.mark.asyncio
async def test_root_endpoint_connected_schema():
    """Test GET / status code 200 and schema validation when DB is connected."""
    db_module.DB_POOL = MagicMock()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "timestamp" in data
    ts = datetime.fromisoformat(data["timestamp"])
    assert ts is not None


# ---------------------------------------------------------------------------
# 2. Database Pool Readiness Check (is_pool_ready)
# ---------------------------------------------------------------------------


def test_is_pool_ready_when_none():
    """Verify is_pool_ready() returns False when DB_POOL is None."""
    db_module.DB_POOL = None
    assert db_module.is_pool_ready() is False


def test_is_pool_ready_when_initialized():
    """Verify is_pool_ready() returns True when DB_POOL is initialized."""
    db_module.DB_POOL = MagicMock()
    assert db_module.is_pool_ready() is True


# ---------------------------------------------------------------------------
# 3. Database Connection Acquisition (get_db_connection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_db_connection_uninitialized_raises_exception():
    """Test that get_db_connection raises RuntimeError when pool is None."""
    db_module.DB_POOL = None
    with pytest.raises(RuntimeError, match="Database pool is not initialized"):
        async for _ in db_module.get_db_connection():
            pass


@pytest.mark.asyncio
async def test_get_db_connection_initialized_yields_connection():
    """Test that get_db_connection yields an active connection when pool is initialized."""
    mock_conn = MagicMock()
    mock_pool = MagicMock()

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_pool.acquire.return_value = AsyncContextManagerMock()
    db_module.DB_POOL = mock_pool

    acquired_conn = None
    async for conn in db_module.get_db_connection():
        acquired_conn = conn

    assert acquired_conn == mock_conn
    mock_pool.acquire.assert_called_once()


# ---------------------------------------------------------------------------
# 4. CORS Middleware Behavior Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_allowed_origin():
    """Verify CORS middleware adds Access-Control-Allow-Origin for allowed origin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_cors_preflight_options_request():
    """Verify CORS preflight OPTIONS request returns correct headers."""
    transport = ASGITransport(app=app)
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.options("/health", headers=headers)

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "GET" in response.headers.get("access-control-allow-methods", "")


@pytest.mark.asyncio
async def test_cors_disallowed_origin():
    """Verify CORS middleware omits Access-Control-Allow-Origin for unauthorized origin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health", headers={"Origin": "http://unauthorized-domain.com"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "http://unauthorized-domain.com"


# ---------------------------------------------------------------------------
# 5. Lifespan Startup & Shutdown Routines Verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_startup_and_shutdown():
    """Verify lifespan context manager triggers DB pool init on startup and close on shutdown."""
    mock_pool = AsyncMock()
    with patch("database.db.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool, \
         patch("database.db.init_db_schema", new_callable=AsyncMock):
        mock_create_pool.return_value = mock_pool

        async with lifespan(app):
            # Verify startup created pool
            mock_create_pool.assert_called_once()
            assert db_module.DB_POOL == mock_pool
            assert db_module.is_pool_ready() is True

        # Verify shutdown closed pool
        mock_pool.close.assert_awaited_once()
        assert db_module.DB_POOL is None
        assert db_module.is_pool_ready() is False


@pytest.mark.asyncio
async def test_init_db_pool_handles_connection_error():
    """Verify init_db_pool catches database connection exceptions gracefully."""
    with patch("database.db.asyncpg.create_pool", side_effect=Exception("Connection refused")):
        await db_module.init_db_pool()

    assert db_module.DB_POOL is None
    assert db_module.is_pool_ready() is False


@pytest.mark.asyncio
async def test_close_db_pool_when_none():
    """Verify close_db_pool executes safely when DB_POOL is already None."""
    db_module.DB_POOL = None
    await db_module.close_db_pool()
    assert db_module.DB_POOL is None
