"""Unit and integration tests for Step 3: Database Schema & Dashboard/Admin APIs."""

from datetime import datetime
import hashlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
from httpx import ASGITransport, AsyncClient
import pytest

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database.db as db_module
from database.scoring import calculate_bayesian_average, calculate_final_score
from main import app


@pytest.fixture(autouse=True)
def setup_mock_db_pool_and_connection():
    """Fixture to mock DB_POOL and override get_db_connection dependency for tests."""
    mock_conn = MagicMock()
    mock_pool = MagicMock()

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_pool.acquire.return_value = AsyncContextManagerMock()
    db_module.DB_POOL = mock_pool

    async def override_get_db_connection():
        yield mock_conn

    app.dependency_overrides[db_module.get_db_connection] = override_get_db_connection
    yield mock_conn
    app.dependency_overrides.clear()
    db_module.DB_POOL = None


# ---------------------------------------------------------------------------
# 1. Scoring Logic Unit Tests (§5.1)
# ---------------------------------------------------------------------------


def test_calculate_bayesian_average_empty():
    """Verify calculate_bayesian_average returns prior mean (5.0) when no ratings exist."""
    avg = calculate_bayesian_average([])
    assert avg == 5.0


def test_calculate_bayesian_average_with_ratings():
    """Verify calculate_bayesian_average calculates correctly for known inputs."""
    # C=5, m=5, ratings=[10, 10, 10, 10, 10] -> n=5, sum=50 -> (25 + 50) / 10 = 7.5
    avg = calculate_bayesian_average([10] * 5)
    assert avg == 7.5


def test_calculate_final_score_basic():
    """Verify calculate_final_score calculates correct weighted score."""
    # ai_score = 80.0, ratings = [10]*5 (raw avg = 7.5, scaled avg = 75.0)
    # final_score = (80.0 * 0.7) + (75.0 * 0.3) = 56.0 + 22.5 = 78.5
    score = calculate_final_score(80.0, [10] * 5)
    assert score == 78.5


def test_calculate_final_score_scale_assertion():
    """Explicitly assert calculate_final_score(100, [10]*20) approaches 100 (not ~73).

    Guards against scale-mismatch regression where ratings (1-10) were not scaled to 0-100.
    """
    score = calculate_final_score(100.0, [10] * 20)
    assert score > 95.0, f"Expected final_score > 95.0, got {score}"
    assert score == 97.0


def test_calculate_final_score_clamping_and_nan_guards():
    """Verify calculate_final_score clamps out-of-bound AI scores and guards against NaN/Inf."""
    assert calculate_final_score(150.0, [5] * 5) == 85.0
    assert calculate_final_score(-50.0, [5] * 5) == 15.0
    assert calculate_final_score(float("nan"), [5] * 5) == 15.0
    assert calculate_final_score(float("inf"), [5] * 5) == 15.0


# ---------------------------------------------------------------------------
# 2. Database Schema DDL Verification (§5.2)
# ---------------------------------------------------------------------------


def test_db_schema_ddl_contains_required_tables_and_indexes():
    """Verify CREATE_TABLES_SQL contains all required table and index definitions."""
    sql = db_module.CREATE_TABLES_SQL
    assert "CREATE TABLE IF NOT EXISTS students" in sql
    assert "CREATE TABLE IF NOT EXISTS projects" in sql
    assert "CREATE TABLE IF NOT EXISTS recruiters" in sql
    assert "CREATE TABLE IF NOT EXISTS project_ratings" in sql
    assert "CREATE TABLE IF NOT EXISTS suggestions" in sql
    assert "CREATE TABLE IF NOT EXISTS notification_logs" in sql
    assert "uq_rating_per_ip_per_day" in sql
    assert "(created_at AT TIME ZONE 'UTC')::date" in sql
    assert "idx_projects_tags" in sql
    assert "idx_recruiters_preference_filters" in sql


# ---------------------------------------------------------------------------
# 3. Student Registration API Integration Tests (§3.1 & §5.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_student_success():
    """Test POST /api/register creates student and project successfully."""
    mock_student = {
        "id": 1,
        "name": "Jane Doe",
        "email": "jane@example.com",
        "github_username": "janedoe",
        "created_at": datetime.now(),
    }
    mock_project = {
        "id": 10,
        "student_id": 1,
        "repo_url": "https://github.com/janedoe/demo",
        "summary": None,
        "tags": [],
        "ai_difficulty": None,
        "ai_authenticity": None,
        "ai_creativity": None,
        "ai_score": None,
        "final_score": None,
        "last_scanned_at": None,
        "created_at": datetime.now(),
    }

    with patch("routers.public.create_student", new_callable=AsyncMock) as mock_create_student, \
         patch("routers.public.create_project", new_callable=AsyncMock) as mock_create_project:

        mock_create_student.return_value = mock_student
        mock_create_project.return_value = mock_project

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "github_username": "janedoe",
                "repo_url": "https://github.com/janedoe/demo",
            }
            response = await ac.post("/api/register", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert data["student"]["name"] == "Jane Doe"
        assert data["project"]["repo_url"] == "https://github.com/janedoe/demo"


@pytest.mark.asyncio
async def test_register_student_duplicate_conflict():
    """Test POST /api/register handles duplicate student error with 400 Bad Request."""
    with patch("routers.public.create_student", new_callable=AsyncMock) as mock_create_student:
        mock_create_student.side_effect = asyncpg.UniqueViolationError("duplicate key value violates unique constraint")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "github_username": "janedoe",
            }
            response = await ac.post("/api/register", json=payload)

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_student_missing_fields_validation_error():
    """Test POST /api/register returns 422 Unprocessable Entity when required fields are missing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"name": "Jane Doe"}
        response = await ac.post("/api/register", json=payload)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. Dashboard Feed API Integration Tests (§3.1 & §5.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dashboard_feed_success():
    """Test GET /api/dashboard returns paginated project feed."""
    mock_feed = {
        "items": [
            {
                "id": 1,
                "student_id": 10,
                "repo_url": "https://github.com/test/repo1",
                "summary": "ML Model",
                "tags": ["python", "ml"],
                "final_score": 92.5,
                "student_name": "Alice",
                "github_username": "alice",
                "student_email": "alice@example.com",
                "ratings_count": 3,
            }
        ],
        "total": 1,
        "page": 1,
        "limit": 10,
    }

    with patch("routers.public.get_projects_feed", new_callable=AsyncMock) as mock_get_feed:
        mock_get_feed.return_value = mock_feed

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/dashboard?page=1&limit=10&min_score=80.0")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["final_score"] == 92.5
        mock_get_feed.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Rating & Scoring API Integration Tests (§3.1 & §5.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_project_success():
    """Test POST /api/rate submits rating and recalculates project score."""
    mock_rating = {
        "id": 5,
        "project_id": 1,
        "rater_type": "public",
        "rater_id": None,
        "rater_ip_hash": hashlib.sha256(b"127.0.0.1").hexdigest(),
        "rating": 9,
        "created_at": datetime.now().isoformat(),
    }

    with patch("routers.public.add_project_rating", new_callable=AsyncMock) as mock_add_rating, \
         patch("routers.public.update_project_score", new_callable=AsyncMock) as mock_update_score:

        mock_add_rating.return_value = mock_rating
        mock_update_score.return_value = 85.0

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {"project_id": 1, "rating": 9}
            response = await ac.post("/api/rate", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert data["rating"]["rating"] == 9
        assert data["new_final_score"] == 85.0


@pytest.mark.asyncio
async def test_rate_project_duplicate_ip_conflict():
    """Test POST /api/rate returns 409 Conflict when unique IP constraint triggers."""
    with patch("routers.public.add_project_rating", new_callable=AsyncMock) as mock_add_rating:
        mock_add_rating.side_effect = asyncpg.UniqueViolationError("duplicate key")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {"project_id": 1, "rating": 8}
            response = await ac.post("/api/rate", json=payload)

        assert response.status_code == 409
        assert "already rated" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rate_project_invalid_rating_value():
    """Test POST /api/rate returns 422 Unprocessable Entity for invalid rating values (<1 or >10)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"project_id": 1, "rating": 15}
        response = await ac.post("/api/rate", json=payload)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 6. Recruiter Flow API Integration Tests (§3.2 & §5.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recruiter_register_success():
    """Test POST /api/recruiter/register creates recruiter profile."""
    mock_recruiter = {
        "id": 1,
        "name": "Recruiter Bob",
        "email": "bob@techcorp.com",
        "preferred_channel": "email",
        "telegram_handle": None,
        "preference_filters": {"min_score": 75.0, "tech_stack": ["python"]},
        "created_at": datetime.now().isoformat(),
    }

    with patch("routers.recruiters.create_recruiter", new_callable=AsyncMock) as mock_create_recruiter:
        mock_create_recruiter.return_value = mock_recruiter

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "name": "Recruiter Bob",
                "email": "bob@techcorp.com",
                "preferred_channel": "email",
                "preference_filters": {"min_score": 75.0, "tech_stack": ["python"]},
            }
            response = await ac.post("/api/recruiter/register", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "bob@techcorp.com"


@pytest.mark.asyncio
async def test_recruiter_register_invalid_channel_validation():
    """Test POST /api/recruiter/register returns 422 when channel is not email or telegram."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "name": "Recruiter Bob",
            "email": "bob@techcorp.com",
            "preferred_channel": "sms",
        }
        response = await ac.post("/api/recruiter/register", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recruiter_register_telegram_missing_handle_validation():
    """Test POST /api/recruiter/register returns 422 when channel is telegram but no handle provided."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "name": "Recruiter Bob",
            "email": "bob@techcorp.com",
            "preferred_channel": "telegram",
        }
        response = await ac.post("/api/recruiter/register", json=payload)

    assert response.status_code == 422
    assert "telegram_handle is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_recruiter_profile_and_matches():
    """Test GET /api/recruiter/{id} retrieves profile and matched projects."""
    mock_recruiter = {
        "id": 1,
        "name": "Recruiter Bob",
        "email": "bob@techcorp.com",
        "preferred_channel": "email",
        "telegram_handle": None,
        "preference_filters": {"min_score": 70.0, "tech_stack": ["python"]},
        "created_at": datetime.now().isoformat(),
    }
    mock_matches = [
        {
            "id": 10,
            "student_id": 2,
            "repo_url": "https://github.com/student/pyproject",
            "summary": "Python API Service",
            "tags": ["python", "fastapi"],
            "final_score": 88.0,
            "student_name": "Charlie",
            "github_username": "charlie",
            "student_email": "charlie@example.com",
        }
    ]

    with patch("routers.recruiters.get_recruiter_by_id", new_callable=AsyncMock) as mock_get_rec, \
         patch("routers.recruiters.get_recruiter_matches", new_callable=AsyncMock) as mock_get_matches:

        mock_get_rec.return_value = mock_recruiter
        mock_get_matches.return_value = mock_matches

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/recruiter/1")

        assert response.status_code == 200
        data = response.json()
        assert data["recruiter"]["name"] == "Recruiter Bob"
        assert len(data["matching_projects"]) == 1
        assert data["matching_projects"][0]["final_score"] == 88.0


@pytest.mark.asyncio
async def test_get_recruiter_profile_not_found():
    """Test GET /api/recruiter/{id} returns 404 Not Found when recruiter does not exist."""
    with patch("routers.recruiters.get_recruiter_by_id", new_callable=AsyncMock) as mock_get_rec:
        mock_get_rec.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/recruiter/999")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_suggestion_success():
    """Test POST /api/suggest submits feedback suggestion."""
    mock_suggestion = {
        "id": 1,
        "project_id": 10,
        "recruiter_id": 1,
        "suggestion_text": "Great work! Consider adding unit tests.",
        "resolved": False,
        "created_at": datetime.now().isoformat(),
    }

    with patch("routers.recruiters.add_suggestion", new_callable=AsyncMock) as mock_add_sugg:
        mock_add_sugg.return_value = mock_suggestion

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "project_id": 10,
                "recruiter_id": 1,
                "suggestion_text": "Great work! Consider adding unit tests.",
            }
            response = await ac.post("/api/suggest", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert data["suggestion"]["suggestion_text"] == "Great work! Consider adding unit tests."


@pytest.mark.asyncio
async def test_create_suggestion_blank_text_validation():
    """Test POST /api/suggest returns 400 Bad Request when suggestion text is only whitespace."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "project_id": 10,
            "recruiter_id": 1,
            "suggestion_text": "   ",
        }
        response = await ac.post("/api/suggest", json=payload)

    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 7. Admin API Stubs Integration Tests (§3.3 & §5.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_scan_stub_success():
    """Test POST /api/admin/scan returns 202 Accepted with queued status."""
    transport = ASGITransport(app=app)
    headers = {"X-Admin-API-Key": "dev_admin_key_12345"}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"project_id": 10}
        response = await ac.post("/api/admin/scan", json=payload, headers=headers)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["project_id"] == 10


@pytest.mark.asyncio
async def test_admin_notify_stub_success():
    """Test POST /api/admin/notify returns 202 Accepted with queued status."""
    transport = ASGITransport(app=app)
    headers = {"X-Admin-API-Key": "dev_admin_key_12345"}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"project_id": 10, "recruiter_id": 1}
        response = await ac.post("/api/admin/notify", json=payload, headers=headers)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["project_id"] == 10
    assert data["recruiter_id"] == 1


@pytest.mark.asyncio
async def test_admin_unauthorized_key():
    """Test admin endpoints return 401 Unauthorized when invalid API key is provided."""
    transport = ASGITransport(app=app)
    headers = {"X-Admin-API-Key": "wrong_key"}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/admin/scan", json={}, headers=headers)

    assert response.status_code == 401
