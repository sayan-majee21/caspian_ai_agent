"""Unit and Integration Tests for TalentCaspian Streamlit Frontend Modules."""

import pytest
import respx
import httpx
from utils.api_client import (
    api_add_project,
    api_add_to_cart,
    api_admin_notify,
    api_admin_scan,
    api_login,
    api_rate_project,
    api_register_recruiter,
    api_register_student,
    api_remove_from_cart,
    api_remove_from_cart_by_item,
    api_submit_peer_suggestion,
    api_submit_suggestion,
    api_trigger_webhook,
    api_update_recruiter_preferences,
    fetch_feed,
    fetch_project_analytics,
    fetch_project_commits,
    fetch_project_detail,
    fetch_project_peer_suggestions,
    fetch_project_ratings,
    fetch_project_suggestions,
    fetch_recruiter_cart,
    fetch_recruiter_profile,
    fetch_recruiter_suggestions,
    fetch_student_profile,
    get_admin_api_key,
    get_backend_url,
)
from utils.auth import (
    get_current_role,
    get_current_user,
    init_session_state,
    is_authenticated,
    login_user_session,
    logout_user_session,
)
from utils.charts import (
    create_commit_activity_chart,
    create_rating_timeline_chart,
    create_recruiter_demand_chart,
    create_score_breakdown_bars,
    create_score_gauge,
)
from utils.ui_components import (
    render_score_badge,
)
import streamlit as st


class TestFrontendAuth:
    """Test suite for authentication session state management."""

    def test_session_state_lifecycle(self):
        """Test initial state, login, and logout session mutations."""
        st.session_state.clear()
        init_session_state()

        assert not is_authenticated()
        assert get_current_user() is None
        assert get_current_role() is None

        # Perform mock student login
        mock_user = {"id": 42, "name": "Test Student", "email": "test@student.edu"}
        login_user_session(mock_user, "student", "mock_token_123")

        assert is_authenticated()
        assert get_current_role() == "student"
        assert get_current_user()["name"] == "Test Student"
        assert st.session_state["user_id"] == 42

        # Perform logout
        logout_user_session()
        assert not is_authenticated()
        assert get_current_role() is None
        assert get_current_user() is None


class TestFrontendCharts:
    """Test suite for Plotly chart generators."""

    def test_score_gauge_creation(self):
        """Test creation of score gauge for different score ranges."""
        fig_high = create_score_gauge(92.0)
        assert fig_high is not None
        assert len(fig_high.data) > 0

        fig_mid = create_score_gauge(72.0)
        assert fig_mid is not None

        fig_low = create_score_gauge(45.0)
        assert fig_low is not None

        fig_none = create_score_gauge(None)
        assert fig_none is not None

    def test_score_breakdown_bars(self):
        """Test horizontal score breakdown bar chart."""
        metrics = [
            {"name": "Technical Quality", "score": 85.0},
            {"name": "Code Authenticity", "score": 90.0},
            {"name": "Project Creativity", "score": 78.0},
        ]
        fig = create_score_breakdown_bars(metrics)
        assert fig is not None
        assert len(fig.data) == 1
        assert len(fig.data[0].x) == 3

    def test_rating_timeline_chart(self):
        """Test rating trajectory chart with empty and populated data."""
        fig_empty = create_rating_timeline_chart([])
        assert fig_empty is not None

        ratings = [
            {"created_at": "2026-08-16T10:00:00Z", "rating": 8, "rater_type": "public"},
            {"created_at": "2026-08-16T11:00:00Z", "rating": 9, "rater_type": "recruiter"},
        ]
        fig = create_rating_timeline_chart(ratings)
        assert fig is not None
        assert len(fig.data) == 2

    def test_commit_activity_chart(self):
        """Test commit activity chart with empty and populated logs."""
        fig_empty = create_commit_activity_chart([])
        assert fig_empty is not None

        commits = [
            {"created_at": "2026-08-16T10:00:00Z", "commit_hash": "a1b2c3d", "change_classification": "major"},
            {"created_at": "2026-08-16T11:00:00Z", "commit_hash": "e4f5g6h", "change_classification": "minor"},
        ]
        fig = create_commit_activity_chart(commits)
        assert fig is not None
        assert len(fig.data) == 1

    def test_recruiter_demand_chart(self):
        """Test recruiter market fit indicator."""
        fig = create_recruiter_demand_chart(5, total_pool=15)
        assert fig is not None
        assert len(fig.data) == 1


class TestFrontendUIComponents:
    """Test suite for UI markup generators."""

    def test_render_score_badge(self):
        """Test HTML score badge rendering."""
        high_badge = render_score_badge(88.5)
        assert "88.5" in high_badge
        assert "rgba(16, 185, 129" in high_badge

        mid_badge = render_score_badge(68.0)
        assert "68.0" in mid_badge

        low_badge = render_score_badge(40.0)
        assert "40.0" in low_badge

        pending_badge = render_score_badge(None)
        assert "Pending AI Scan" in pending_badge


class TestFrontendApiClient:
    """Test suite for API client HTTP wrappers using respx."""

    @respx.mock
    def test_api_login_success(self):
        """Test student login request handling."""
        backend_url = get_backend_url()
        respx.post(f"{backend_url}/api/login").respond(
            status_code=200,
            json={
                "status": "success",
                "user_type": "student",
                "user": {"id": 1, "name": "Krishna", "email": "krishna@example.com"},
                "token": "tok_123",
            },
        )
        res = api_login("krishna@example.com", "student")
        assert res["status"] == "success"
        assert res["user"]["name"] == "Krishna"

    @respx.mock
    def test_api_register_student_success(self):
        """Test student registration request."""
        backend_url = get_backend_url()
        respx.post(f"{backend_url}/api/register").respond(
            status_code=201,
            json={
                "status": "success",
                "student": {"id": 10, "name": "Alex", "email": "alex@dev.io", "github_username": "alexdev"},
                "project": {"id": 20, "repo_url": "https://github.com/alexdev/app"},
            },
        )
        res = api_register_student("Alex", "alex@dev.io", "alexdev", "https://github.com/alexdev/app")
        assert res["status"] == "success"
        assert res["student"]["id"] == 10

    @respx.mock
    def test_api_register_recruiter_success(self):
        """Test recruiter registration request."""
        backend_url = get_backend_url()
        respx.post(f"{backend_url}/api/recruiter/register").respond(
            status_code=201,
            json={
                "id": 5,
                "name": "Sarah Recruiter",
                "email": "sarah@hiring.com",
                "preferred_channel": "telegram",
                "telegram_handle": "@sarah_rec",
            },
        )
        res = api_register_recruiter(
            name="Sarah Recruiter",
            email="sarah@hiring.com",
            preferred_channel="telegram",
            telegram_handle="@sarah_rec",
            preference_filters={"tech_stack": ["python"], "min_score": 80},
        )
        assert res["id"] == 5

    @respx.mock
    def test_fetch_feed_success(self):
        """Test project discovery feed fetching."""
        backend_url = get_backend_url()
        respx.get(f"{backend_url}/api/dashboard").respond(
            status_code=200,
            json={
                "items": [{"id": 1, "repo_url": "https://github.com/test/repo", "final_score": 88.0}],
                "total": 1,
                "page": 1,
                "limit": 10,
            },
        )
        res = fetch_feed(page=1, limit=10)
        assert len(res["items"]) == 1
        assert res["items"][0]["id"] == 1

    @respx.mock
    def test_api_admin_scan_and_notify(self):
        """Test admin trigger endpoints."""
        backend_url = get_backend_url()
        respx.post(f"{backend_url}/api/admin/scan").respond(
            status_code=202,
            json={"status": "queued", "message": "AI scanning process queued"},
        )
        respx.post(f"{backend_url}/api/admin/notify").respond(
            status_code=202,
            json={"status": "queued", "message": "Notification process queued"},
        )

        scan_res = api_admin_scan(project_id=1)
        assert scan_res["status"] == "queued"

        notify_res = api_admin_notify(project_id=1, recruiter_id=2)
        assert notify_res["status"] == "queued"
