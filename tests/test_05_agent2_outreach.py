"""Unit and Integration Tests for Step 5 — Agent 2: Matching & Caspian Outreach."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from database.db import (
    create_notification_log,
    has_recent_notification,
)
from services.caspian_outreach import dispatch_message
from services.matching_engine import find_candidate_projects, find_matches
from services.notification_service import (
    process_notifications,
    send_followup_notification,
)
from services.outreach_service import (
    _get_matching_tags,
    generate_followup_message,
    generate_outreach_message,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: Matching Engine & Boundary Edge Cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_matching_engine():
    """Verify find_matches and find_candidate_projects delegate to DB layer correctly."""
    mock_conn = AsyncMock()

    # Mock DB returns for project matching recruiters
    mock_conn.fetch.side_effect = [
        [
            {
                "id": 1,
                "name": "Alice Recruiter",
                "email": "alice@techcorp.com",
                "preferred_channel": "email",
                "telegram_handle": None,
                "preference_filters": '{"tech_stack": ["python"], "min_score": 70}',
                "created_at": None,
            }
        ],
        [
            {
                "id": 10,
                "student_id": 1,
                "repo_url": "https://github.com/student/repo1",
                "summary": "Python backend API",
                "tags": '["python", "fastapi"]',
                "ai_difficulty": 80.0,
                "ai_authenticity": 85.0,
                "ai_creativity": 75.0,
                "ai_score": 80.0,
                "final_score": 82.0,
                "last_scanned_at": None,
                "created_at": None,
                "student_name": "Bob Student",
                "github_username": "bobstudent",
                "student_email": "bob@student.edu",
            }
        ],
    ]

    matched_recruiters = await find_matches(mock_conn, project_id=10)
    assert len(matched_recruiters) == 1
    assert matched_recruiters[0]["name"] == "Alice Recruiter"
    assert matched_recruiters[0]["preference_filters"] == {"tech_stack": ["python"], "min_score": 70}

    matched_projects = await find_candidate_projects(mock_conn, recruiter_id=1)
    assert len(matched_projects) == 1
    assert matched_projects[0]["student_name"] == "Bob Student"
    assert matched_projects[0]["tags"] == ["python", "fastapi"]


@pytest.mark.asyncio
async def test_matching_engine_empty_tech_stack_and_filters():
    """Verify matching engine handles empty tech_stack, None, and empty JSONB preference filters."""
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        {
            "id": 2,
            "name": "General Recruiter",
            "email": "general@recruiting.com",
            "preferred_channel": "email",
            "telegram_handle": None,
            "preference_filters": "{}",
            "created_at": None,
        }
    ]

    matched = await find_matches(mock_conn, project_id=99)
    assert len(matched) == 1
    assert matched[0]["name"] == "General Recruiter"
    assert matched[0]["preference_filters"] == {}


@pytest.mark.asyncio
async def test_matching_engine_min_score_boundary_conditions():
    """Verify min_score boundary conditions (>= min_score threshold)."""
    mock_conn = AsyncMock()

    # Case: Project score equal to min_score (75.0 == 75.0) -> match
    mock_conn.fetch.side_effect = [
        [
            {
                "id": 3,
                "name": "Boundary Recruiter",
                "email": "boundary@test.com",
                "preferred_channel": "email",
                "telegram_handle": None,
                "preference_filters": '{"min_score": 75.0}',
                "created_at": None,
            }
        ],
        [],  # Sub-threshold score (74.9 < 75.0) -> no match returned by DB
    ]

    matched_exact = await find_matches(mock_conn, project_id=100)
    assert len(matched_exact) == 1

    matched_below = await find_matches(mock_conn, project_id=101)
    assert len(matched_below) == 0


# ---------------------------------------------------------------------------
# Test 2: Outreach Generation & Gemini Fallback Edge Cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outreach_generation():
    """Verify prompt context injection and output format for outreach and follow-up messages."""
    recruiter = {
        "id": 1,
        "name": "Jane Recruiter",
        "email": "jane@company.com",
        "preferred_channel": "email",
        "preference_filters": {"tech_stack": ["python", "react"], "min_score": 75},
    }
    project = {
        "id": 5,
        "student_name": "Alex Dev",
        "repo_url": "https://github.com/alex/smart-api",
        "summary": "An intelligent FastAPI backend for data pipeline analytics.",
        "tags": ["python", "fastapi", "postgresql"],
    }

    # Test fallback message generation (no API key set)
    msg = await generate_outreach_message(recruiter, project)
    assert "Jane Recruiter" in msg
    assert "Alex Dev" in msg
    assert "https://github.com/alex/smart-api" in msg
    assert "python" in msg
    assert "http://localhost:3000/dashboard" in msg

    # Test follow-up message generation
    followup_msg = generate_followup_message(
        recruiter, project, suggestion_text="add unit tests for auth module"
    )
    assert "Hi Jane Recruiter" in followup_msg
    assert "Alex Dev" in followup_msg
    assert "smart-api" in followup_msg
    assert "add unit tests for auth module" in followup_msg


@pytest.mark.asyncio
async def test_outreach_generation_gemini_exception_fallback():
    """Verify outreach service safely catches Gemini API exceptions and returns fallback message."""
    recruiter = {
        "id": 1,
        "name": "Dave Recruiter",
        "email": "dave@tech.com",
        "preference_filters": {"tech_stack": ["python"]},
    }
    project = {
        "id": 5,
        "student_name": "Eve Student",
        "repo_url": "https://github.com/eve/ml-pipeline",
        "summary": "ML pipeline for telemetry",
        "tags": ["python", "pytorch"],
    }

    # Mock google.genai raising an Exception
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("Gemini API Rate Limit Exceeded"))
        mock_client_cls.return_value = mock_client

        msg = await generate_outreach_message(recruiter, project, api_key="fake_key")


        assert "Hi Dave Recruiter" in msg
        assert "Eve Student" in msg
        assert "ml-pipeline" in msg


def test_matching_tags_helper():
    """Verify _get_matching_tags helper functions with various input formats and case insensitivity."""
    recruiter_json_pref = {
        "preference_filters": '{"tech_stack": ["PYTHON", "Docker"]}'
    }
    project_str_tags = {
        "tags": '["python", "fastapi", "docker"]'
    }

    matched = _get_matching_tags(recruiter_json_pref, project_str_tags)
    assert "python" in matched
    assert "docker" in matched

    # Case: Empty recruiter tech stack -> returns all project tags
    empty_rec = {"preference_filters": {}}
    assert _get_matching_tags(empty_rec, project_str_tags) == ["python", "fastapi", "docker"]


# ---------------------------------------------------------------------------
# Test 3: Caspian Outreach Dispatching & Exception Handling
# ---------------------------------------------------------------------------
def test_caspian_dispatch():
    """Verify dispatch_message routes to correct recipient and channel via CommClient."""
    mock_client = MagicMock()
    mock_client.send_message.return_value = {"status": "sent", "id": "msg_123"}

    # Email recruiter
    recruiter_email = {
        "id": 1,
        "name": "Sam Recruiter",
        "email": "sam@hr.com",
        "preferred_channel": "email",
        "telegram_handle": "@sam_hr",
    }
    res_email = dispatch_message(recruiter_email, "Hello email recruiter", client=mock_client)
    assert res_email == {"status": "sent", "id": "msg_123"}
    mock_client.send_message.assert_called_with(
        channel="email", recipient="sam@hr.com", content="Hello email recruiter"
    )

    # Telegram recruiter
    recruiter_telegram = {
        "id": 2,
        "name": "Tina Recruiter",
        "email": "tina@hr.com",
        "preferred_channel": "telegram",
        "telegram_handle": "@tina_recruiter",
    }
    res_tg = dispatch_message(recruiter_telegram, "Hello telegram recruiter", client=mock_client)
    assert res_tg == {"status": "sent", "id": "msg_123"}
    mock_client.send_message.assert_called_with(
        channel="telegram", recipient="@tina_recruiter", content="Hello telegram recruiter"
    )


def test_caspian_dispatch_telegram_fallback_and_exception():
    """Verify telegram falls back to email if handle missing, and handles client exceptions cleanly."""
    mock_client = MagicMock()

    # Telegram channel with missing handle -> fallback recipient to email
    recruiter_no_handle = {
        "id": 3,
        "name": "NoHandle",
        "email": "nohandle@hr.com",
        "preferred_channel": "telegram",
        "telegram_handle": None,
    }
    mock_client.send_message.return_value = {"status": "sent"}
    res = dispatch_message(recruiter_no_handle, "Test msg", client=mock_client)
    mock_client.send_message.assert_called_with(
        channel="email", recipient="nohandle@hr.com", content="Test msg"
    )


    # Client exception handling
    mock_client.send_message.side_effect = RuntimeError("SDK Network Error")
    res_err = dispatch_message(recruiter_no_handle, "Test msg", client=mock_client)
    assert res_err["status"] == "failed"
    assert "SDK Network Error" in res_err["error"]


# ---------------------------------------------------------------------------
# Test 4: Deduplication Check & Cooldown Logic
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deduplication():
    """Verify 7-day cooldown prevents duplicate standard notifications but allows follow-ups."""
    mock_conn = AsyncMock()

    # Case 1: Recruiter notified recently (has_recent_notification returns True)
    mock_conn.fetchval.return_value = True

    is_recent = await has_recent_notification(mock_conn, recruiter_id=1, project_id=5, within_days=7)
    assert is_recent is True

    mock_client = MagicMock()
    mock_client.send_message.return_value = {"status": "sent"}

    # Mock DB functions inside notification_service
    with (
        patch("database.db.get_project_by_id", new_callable=AsyncMock) as mock_get_proj,
        patch("database.db.get_recruiter_by_id", new_callable=AsyncMock) as mock_get_rec,
        patch("database.db.has_recent_notification", new_callable=AsyncMock) as mock_has_rec,
        patch("database.db.create_notification_log", new_callable=AsyncMock) as mock_create_log,
    ):
        mock_get_proj.return_value = {
            "id": 5,
            "student_name": "Alex",
            "repo_url": "https://github.com/alex/repo",
            "summary": "Project summary",
            "tags": ["python"],
        }
        mock_get_rec.return_value = {
            "id": 1,
            "name": "Jane",
            "email": "jane@co.com",
            "preferred_channel": "email",
        }
        mock_has_rec.return_value = True  # Recent notification exists within 7 days

        # Process standard notification -> Should skip due to 7-day cooldown
        res_standard = await process_notifications(
            project_id=5, recruiter_id=1, pool=mock_conn, client=mock_client
        )
        assert res_standard["processed_count"] == 0
        assert res_standard["skipped_count"] == 1
        mock_client.send_message.assert_not_called()

        # Follow-up notification -> Should bypass cooldown and dispatch
        res_followup = await send_followup_notification(
            recruiter_id=1,
            project_id=5,
            suggestion_text="Fix error handling",
            pool=mock_conn,
            client=mock_client,
        )
        assert res_followup["status"] == "completed"
        assert res_followup["is_followup"] is True
        mock_client.send_message.assert_called_once()
        mock_create_log.assert_called_once_with(
            mock_conn, recruiter_id=1, project_id=5, channel="email", is_followup=True
        )


# ---------------------------------------------------------------------------
# Test 5: Follow-Up Flow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_followup_flow():
    """Verify send_followup_notification formats message and logs with is_followup=True."""
    mock_conn = AsyncMock()
    mock_client = MagicMock()
    mock_client.send_message.return_value = {"status": "sent", "id": "msg_followup_1"}

    with (
        patch("database.db.get_project_by_id", new_callable=AsyncMock) as mock_get_proj,
        patch("database.db.get_recruiter_by_id", new_callable=AsyncMock) as mock_get_rec,
        patch("database.db.create_notification_log", new_callable=AsyncMock) as mock_create_log,
    ):
        mock_get_proj.return_value = {
            "id": 8,
            "student_name": "Charlie",
            "repo_url": "https://github.com/charlie/awesome-app",
            "summary": "Awesome App",
        }
        mock_get_rec.return_value = {
            "id": 2,
            "name": "Dave Recruiter",
            "email": "dave@corp.com",
            "preferred_channel": "email",
        }

        res = await send_followup_notification(
            recruiter_id=2,
            project_id=8,
            suggestion_text="Add OpenAPI docs",
            pool=mock_conn,
            client=mock_client,
        )

        assert res["status"] == "completed"
        assert res["is_followup"] is True
        mock_client.send_message.assert_called_once_with(
            channel="email",
            recipient="dave@corp.com",
            content="Hi Dave Recruiter, Student Charlie has updated 'awesome-app' addressing your feedback regarding Add OpenAPI docs!",
        )
        mock_create_log.assert_called_once_with(
            mock_conn, recruiter_id=2, project_id=8, channel="email", is_followup=True
        )


# ---------------------------------------------------------------------------
# Test 6: Endpoint Authorization & Background Execution
# ---------------------------------------------------------------------------
def test_admin_notify_endpoint():
    """Verify POST /api/admin/notify authorization and background execution queuing."""
    # 1. Unauthorized call (missing header)
    resp_no_key = client.post("/api/admin/notify", json={"project_id": 1})
    assert resp_no_key.status_code == 401

    # 2. Unauthorized call (invalid header)
    resp_invalid = client.post(
        "/api/admin/notify",
        json={"project_id": 1},
        headers={"X-Admin-API-Key": "wrong_key"},
    )
    assert resp_invalid.status_code == 401

    # 3. Invalid payload (missing project_id)
    resp_bad_body = client.post(
        "/api/admin/notify",
        json={},
        headers={"X-Admin-API-Key": "dev_admin_key_12345"},
    )
    assert resp_bad_body.status_code == 422

    # 4. Authorized call with valid header
    with patch("routers.admin.process_notifications") as mock_proc:
        resp_valid = client.post(
            "/api/admin/notify",
            json={"project_id": 1, "recruiter_id": 2},
            headers={"X-Admin-API-Key": "dev_admin_key_12345"},
        )
        assert resp_valid.status_code == 202
        data = resp_valid.json()
        assert data["status"] == "queued"
        assert data["project_id"] == 1
        assert data["recruiter_id"] == 2
