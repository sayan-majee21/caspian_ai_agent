"""Unit and integration tests for Personal Analytics & Recruiter workflow endpoints."""

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
# 1. Authentication & Login Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_student_success():
    """Test POST /api/login for student returns user profile and session token."""
    mock_student = {
        "id": 1,
        "name": "Jane Doe",
        "email": "jane@example.com",
        "github_username": "janedoe",
        "created_at": datetime.now().isoformat(),
    }
    with patch("routers.public.get_student_by_email", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_student

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/login",
                json={"email": "jane@example.com", "user_type": "student"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["user_type"] == "student"
        assert data["user"]["name"] == "Jane Doe"
        assert "stu_session_1_" in data["token"]


@pytest.mark.asyncio
async def test_login_recruiter_success():
    """Test POST /api/login for recruiter returns recruiter profile and session token."""
    mock_recruiter = {
        "id": 2,
        "name": "Bob Recruiter",
        "email": "bob@techcorp.com",
        "preferred_channel": "email",
        "telegram_handle": None,
        "preference_filters": {"min_score": 75.0},
        "created_at": datetime.now().isoformat(),
    }
    with patch("routers.public.get_recruiter_by_contact", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_recruiter

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/login",
                json={"email": "bob@techcorp.com", "user_type": "recruiter"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["user_type"] == "recruiter"
        assert data["user"]["name"] == "Bob Recruiter"
        assert "rec_session_2_" in data["token"]


@pytest.mark.asyncio
async def test_login_user_not_found():
    """Test POST /api/login returns 404 when email does not exist."""
    with patch("routers.public.get_student_by_email", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/login",
                json={"email": "nonexistent@example.com", "user_type": "student"},
            )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 2. Student Portfolio & Projects Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_student_profile_success():
    """Test GET /api/student/{id} retrieves full student profile and project portfolio."""
    mock_profile = {
        "student": {
            "id": 1,
            "name": "Jane Doe",
            "email": "jane@example.com",
            "github_username": "janedoe",
            "created_at": datetime.now().isoformat(),
        },
        "projects": [
            {
                "id": 10,
                "student_id": 1,
                "repo_url": "https://github.com/janedoe/fastapi-app",
                "summary": "FastAPI Web App",
                "tags": ["python", "fastapi"],
                "final_score": 90.0,
                "ai_score": 88.0,
            }
        ],
        "total_projects": 1,
        "top_score": 90.0,
        "average_score": 90.0,
    }
    with patch("routers.public.get_student_profile", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_profile

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/student/1")

        assert response.status_code == 200
        data = response.json()
        assert data["student"]["name"] == "Jane Doe"
        assert len(data["projects"]) == 1
        assert data["top_score"] == 90.0


@pytest.mark.asyncio
async def test_get_student_profile_not_found():
    """Test GET /api/student/{id} returns 404 when student does not exist."""
    with patch("routers.public.get_student_profile", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/student/999")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_second_project_for_existing_student():
    """Test POST /api/projects successfully adds another project for already registered student."""
    mock_student = {
        "id": 1,
        "name": "Jane Doe",
        "email": "jane@example.com",
        "github_username": "janedoe",
    }
    mock_project = {
        "id": 12,
        "student_id": 1,
        "repo_url": "https://github.com/janedoe/second-project",
        "summary": None,
        "tags": [],
        "final_score": None,
    }
    with (
        patch("routers.public.get_student_by_id", new_callable=AsyncMock) as mock_get_st,
        patch("routers.public.create_project", new_callable=AsyncMock) as mock_cr_proj,
        patch("routers.public.scan_and_evaluate_project_bg", new_callable=AsyncMock),
    ):
        mock_get_st.return_value = mock_student
        mock_cr_proj.return_value = mock_project

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "student_id": 1,
                "repo_url": "https://github.com/janedoe/second-project",
            }
            response = await ac.post("/api/projects", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert data["project"]["id"] == 12


@pytest.mark.asyncio
async def test_add_project_student_not_found():
    """Test POST /api/projects returns 404 when target student ID does not exist."""
    with patch("routers.public.get_student_by_id", new_callable=AsyncMock) as mock_get_st:
        mock_get_st.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "student_id": 999,
                "repo_url": "https://github.com/janedoe/second-project",
            }
            response = await ac.post("/api/projects", json=payload)

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 3. Single Project & Personal Analytics Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_single_project():
    """Test GET /api/project/{id} retrieves full single project details."""
    mock_project = {
        "id": 10,
        "student_id": 1,
        "repo_url": "https://github.com/janedoe/demo",
        "summary": "Demo Project",
        "tags": ["python"],
        "ai_difficulty": 80.0,
        "ai_authenticity": 85.0,
        "ai_creativity": 90.0,
        "ai_score": 84.5,
        "final_score": 86.0,
        "student_name": "Jane Doe",
        "github_username": "janedoe",
        "student_email": "jane@example.com",
    }
    with (
        patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get,
        patch("routers.public.find_matches", new_callable=AsyncMock) as mock_matches,
        patch("routers.public.get_project_peer_suggestions", new_callable=AsyncMock) as mock_peer,
    ):
        mock_get.return_value = mock_project
        mock_matches.return_value = [{"id": 1}]
        mock_peer.return_value = []

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/10")

        assert response.status_code == 200
        data = response.json()
        assert data["project"]["id"] == 10
        assert data["project"]["student_name"] == "Jane Doe"
        assert data["recruiter_interest_count"] == 1
        assert len(data["metrics"]) == 3


@pytest.mark.asyncio
async def test_get_single_project_not_found():
    """Test GET /api/project/{id} returns 404 when project does not exist."""
    with patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/999")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_feed_preview_and_tag_filtering():
    """Test GET /api/feed supports preview mode and tag filtering."""
    mock_feed = {
        "items": [
            {
                "id": 10,
                "project_name": "demo",
                "summary": "Demo Project",
                "tags": ["python"],
                "final_score": 86.0,
                "preview_only": True,
            }
        ],
        "total": 1,
        "page": 1,
        "limit": 10,
    }
    with patch("routers.public.get_projects_feed", new_callable=AsyncMock) as mock_feed_fn:
        mock_feed_fn.return_value = mock_feed

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/feed?tag=python&preview=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["preview_only"] is True


@pytest.mark.asyncio
async def test_get_project_analytics():
    """Test GET /api/project/{id}/analytics returns complete Personal Analytics bundle."""
    mock_analytics = {
        "header": {
            "project_id": 10,
            "project_name": "demo",
            "repo_url": "https://github.com/janedoe/demo",
            "status": "Active",
            "student_name": "Jane Doe",
        },
        "score_hero": {
            "final_score": 87.0,
            "ai_score": 84.0,
            "score_change": 3.0,
            "confidence": "High",
            "classification": "High-Rated Project",
        },
        "metrics": [
            {"name": "Technical Quality", "score": 85.0},
            {"name": "Code Authenticity", "score": 82.0},
            {"name": "Project Creativity", "score": 86.0},
        ],
        "summary": {"text": "Clean modular codebase", "tags": ["python", "fastapi"]},
        "evolution": {"rating_history": [], "commits": [], "total_commits": 0},
        "recruiter_interest": {"matched_recruiter_count": 3, "category_distribution": {"python": 3}},
        "recruiter_suggestions": [],
        "peer_suggestions": [],
        "ai_recommendations": [
            {"title": "Enhance Technical Depth", "impact": "High"}
        ],
    }
    with patch("routers.public.get_project_analytics", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_analytics

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/10/analytics")

        assert response.status_code == 200
        data = response.json()
        assert data["header"]["project_name"] == "demo"
        assert data["score_hero"]["final_score"] == 87.0
        assert len(data["metrics"]) == 3
        assert data["recruiter_interest"]["matched_recruiter_count"] == 3


@pytest.mark.asyncio
async def test_get_project_analytics_not_found():
    """Test GET /api/project/{id}/analytics returns 404 when project does not exist."""
    with patch("routers.public.get_project_analytics", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/999/analytics")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_project_ratings_history():
    """Test GET /api/project/{id}/ratings returns timestamped ratings list."""
    mock_project = {"id": 10}
    mock_ratings = [
        {"id": 1, "project_id": 10, "rater_type": "public", "rating": 9, "created_at": datetime.now().isoformat()},
        {"id": 2, "project_id": 10, "rater_type": "recruiter", "rating": 8, "created_at": datetime.now().isoformat()},
    ]
    with (
        patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get_p,
        patch("routers.public.get_project_ratings_history", new_callable=AsyncMock) as mock_get_r,
    ):
        mock_get_p.return_value = mock_project
        mock_get_r.return_value = mock_ratings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/10/ratings")

        assert response.status_code == 200
        data = response.json()
        assert len(data["ratings"]) == 2
        assert data["average_rating"] == 8.5


@pytest.mark.asyncio
async def test_get_project_ratings_not_found():
    """Test GET /api/project/{id}/ratings returns 404 when project does not exist."""
    with patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get_p:
        mock_get_p.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/999/ratings")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_project_commits_history():
    """Test GET /api/project/{id}/commits returns commits list."""
    mock_project = {"id": 10}
    mock_commits = [
        {
            "id": 1,
            "project_id": 10,
            "commit_hash": "a1b2c3d",
            "commit_message": "feat: add Dockerfile",
            "author_name": "janedoe",
            "classification": "Major",
        }
    ]
    with (
        patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get_p,
        patch("routers.public.get_project_commit_logs", new_callable=AsyncMock) as mock_get_c,
    ):
        mock_get_p.return_value = mock_project
        mock_get_c.return_value = mock_commits

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/10/commits")

        assert response.status_code == 200
        data = response.json()
        assert len(data["commits"]) == 1
        assert data["commits"][0]["commit_hash"] == "a1b2c3d"


@pytest.mark.asyncio
async def test_get_project_commits_not_found():
    """Test GET /api/project/{id}/commits returns 404 when project does not exist."""
    with patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get_p:
        mock_get_p.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/999/commits")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_project_suggestions_list():
    """Test GET /api/project/{id}/suggestions retrieves recruiter feedback suggestions."""
    mock_project = {"id": 10}
    mock_suggestions = [
        {
            "id": 1,
            "project_id": 10,
            "recruiter_id": 2,
            "recruiter_name": "Bob",
            "suggestion_text": "Add unit tests",
            "resolved": False,
            "status": "Open",
            "priority": "High",
        }
    ]
    with (
        patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get_p,
        patch("routers.public.get_project_suggestions", new_callable=AsyncMock) as mock_get_s,
    ):
        mock_get_p.return_value = mock_project
        mock_get_s.return_value = mock_suggestions

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/project/10/suggestions")

        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["status"] == "Open"


@pytest.mark.asyncio
async def test_peer_suggestions_crud():
    """Test POST and GET /api/project/{id}/peer-suggestions for peer community feedback."""
    mock_project = {"id": 10}
    mock_created = {
        "id": 1,
        "project_id": 10,
        "student_id": 3,
        "student_name": "Krishna",
        "feedback_text": "Great architecture, consider adding dark mode.",
        "created_at": datetime.now().isoformat(),
    }
    with (
        patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get_p,
        patch("routers.public.add_peer_suggestion", new_callable=AsyncMock) as mock_add_peer,
        patch("routers.public.get_project_peer_suggestions", new_callable=AsyncMock) as mock_get_peer,
    ):
        mock_get_p.return_value = mock_project
        mock_add_peer.return_value = mock_created
        mock_get_peer.return_value = [mock_created]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Submit peer feedback
            payload = {
                "student_id": 3,
                "student_name": "Krishna",
                "feedback_text": "Great architecture, consider adding dark mode.",
            }
            res_post = await ac.post("/api/project/10/peer-suggestions", json=payload)
            assert res_post.status_code == 201
            assert res_post.json()["status"] == "success"

            # Retrieve peer feedback thread
            res_get = await ac.get("/api/project/10/peer-suggestions")
            assert res_get.status_code == 200
            assert len(res_get.json()["peer_suggestions"]) == 1


@pytest.mark.asyncio
async def test_peer_suggestions_project_not_found():
    """Test POST /api/project/{id}/peer-suggestions returns 404 when project does not exist."""
    with patch("routers.public.get_project_by_id", new_callable=AsyncMock) as mock_get_p:
        mock_get_p.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "student_id": 3,
                "student_name": "Krishna",
                "feedback_text": "Nice project!",
            }
            response = await ac.post("/api/project/999/peer-suggestions", json=payload)

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 4. Recruiter Suggestions History, Preferences & Cart Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recruiter_suggestions_history():
    """Test GET /api/recruiter/{id}/suggestions retrieves recruiter's submitted suggestions with resolution status."""
    mock_recruiter = {"id": 1, "name": "Bob"}
    mock_history = [
        {
            "id": 5,
            "project_id": 10,
            "recruiter_id": 1,
            "suggestion_text": "Add Docker setup",
            "resolved": True,
            "status": "Resolved",
            "repo_url": "https://github.com/janedoe/demo",
            "project_summary": "Demo Project",
            "project_score": 88.0,
            "student_name": "Jane Doe",
            "github_username": "janedoe",
        }
    ]
    with (
        patch("routers.recruiters.get_recruiter_by_id", new_callable=AsyncMock) as mock_get_r,
        patch("routers.recruiters.get_recruiter_suggestions", new_callable=AsyncMock) as mock_get_suggs,
    ):
        mock_get_r.return_value = mock_recruiter
        mock_get_suggs.return_value = mock_history

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/recruiter/1/suggestions")

        assert response.status_code == 200
        data = response.json()
        assert data["recruiter_id"] == 1
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["resolved"] is True
        assert data["suggestions"][0]["status"] == "Resolved"


@pytest.mark.asyncio
async def test_get_recruiter_suggestions_not_found():
    """Test GET /api/recruiter/{id}/suggestions returns 404 when recruiter does not exist."""
    with patch("routers.recruiters.get_recruiter_by_id", new_callable=AsyncMock) as mock_get_r:
        mock_get_r.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/recruiter/999/suggestions")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_recruiter_preferences():
    """Test PATCH /api/recruiter/{id}/preferences updates matching filters."""
    mock_updated = {
        "id": 1,
        "name": "Bob",
        "email": "bob@techcorp.com",
        "preferred_channel": "telegram",
        "preference_filters": {"min_score": 85.0, "tech_stack": ["python", "fastapi", "docker"]},
    }
    with patch("routers.recruiters.update_recruiter_preferences", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = mock_updated

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "preference_filters": {"min_score": 85.0, "tech_stack": ["python", "fastapi", "docker"]}
            }
            response = await ac.patch("/api/recruiter/1/preferences", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["recruiter"]["preference_filters"]["min_score"] == 85.0


@pytest.mark.asyncio
async def test_recruiter_cart_crud():
    """Test recruiter cart: add to cart, list cart items, and delete from cart."""
    mock_recruiter = {"id": 1, "name": "Bob"}
    mock_cart_item = {"id": 100, "recruiter_id": 1, "project_id": 10, "created_at": datetime.now().isoformat()}
    mock_cart_list = [
        {
            "id": 100,
            "recruiter_id": 1,
            "project_id": 10,
            "added_at": datetime.now().isoformat(),
            "project": {
                "id": 10,
                "repo_url": "https://github.com/janedoe/demo",
                "summary": "Demo Project",
                "final_score": 88.0,
                "student": {"id": 1, "name": "Jane Doe"},
            },
        }
    ]

    with (
        patch("routers.recruiters.get_recruiter_by_id", new_callable=AsyncMock) as mock_get_r,
        patch("routers.recruiters.add_to_cart", new_callable=AsyncMock) as mock_add_cart,
        patch("routers.recruiters.get_cart_items", new_callable=AsyncMock) as mock_get_cart,
        patch("routers.recruiters.remove_cart_item_by_id", new_callable=AsyncMock) as mock_del_item,
        patch("routers.recruiters.remove_from_cart", new_callable=AsyncMock) as mock_del_cart,
    ):
        mock_get_r.return_value = mock_recruiter
        mock_add_cart.return_value = mock_cart_item
        mock_get_cart.return_value = mock_cart_list
        mock_del_item.return_value = True
        mock_del_cart.return_value = True

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Add to cart
            res_add = await ac.post("/api/cart", json={"recruiter_id": 1, "project_id": 10})
            assert res_add.status_code == 201
            assert res_add.json()["cart_item"]["id"] == 100

            # 2. Get cart items
            res_get = await ac.get("/api/cart/1")
            assert res_get.status_code == 200
            assert len(res_get.json()["cart_items"]) == 1

            # 3. Delete by item ID
            res_del_item = await ac.delete("/api/cart/100")
            assert res_del_item.status_code == 200

            # 4. Delete by recruiter & project ID
            res_del_proj = await ac.delete("/api/cart/1/10")
            assert res_del_proj.status_code == 200


@pytest.mark.asyncio
async def test_delete_cart_item_not_found():
    """Test DELETE /api/cart/{item_id} returns 404 when item does not exist."""
    with patch("routers.recruiters.remove_cart_item_by_id", new_callable=AsyncMock) as mock_del:
        mock_del.return_value = False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.delete("/api/cart/999")

        assert response.status_code == 404
