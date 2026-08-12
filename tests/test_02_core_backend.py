"""Tests for Step 2: Core Backend Setup."""

import pytest
from httpx import AsyncClient, ASGITransport
from main import app
import database.db as db_module


@pytest.mark.asyncio
async def test_health_check():
    """Test /health endpoint status code and response payload structure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["database"] in ["connected", "disconnected"]


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test / root endpoint status code and response payload structure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["database"] in ["connected", "disconnected"]


def test_is_pool_ready():
    """Test is_pool_ready helper function reflection of DB_POOL state."""
    db_module.DB_POOL = None
    assert db_module.is_pool_ready() is False


@pytest.mark.asyncio
async def test_get_db_connection_uninitialized():
    """Test that get_db_connection raises RuntimeError when pool is None."""
    db_module.DB_POOL = None
    with pytest.raises(RuntimeError, match="Database pool is not initialized"):
        async for _ in db_module.get_db_connection():
            pass
