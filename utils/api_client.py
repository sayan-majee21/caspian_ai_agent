"""Centralized synchronous API client for TalentCaspian FastAPI backend."""

import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx
import streamlit as st

logger = logging.getLogger("talentcaspian.frontend.api")

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_ADMIN_KEY = "dev_admin_key_12345"


def get_backend_url() -> str:
    """Retrieve base backend API URL from environment or fallback default.

    Returns:
        str: Clean base URL without trailing slash.
    """
    url = os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL)
    return url.rstrip("/")


def get_admin_api_key() -> str:
    """Retrieve configured Admin API Key from environment or default.

    Returns:
        str: Admin API Key string.
    """
    return os.getenv("ADMIN_API_KEY", DEFAULT_ADMIN_KEY)


def _build_client() -> httpx.Client:
    """Create a configured synchronous httpx client.

    Returns:
        httpx.Client: Configured HTTP client instance.
    """
    return httpx.Client(
        base_url=get_backend_url(),
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"Accept": "application/json"},
    )


def clear_api_cache() -> None:
    """Clear all Streamlit data caches for immediate live refresh."""
    st.cache_data.clear()


# ==========================================
# 1. AUTHENTICATION & REGISTRATION
# ==========================================


def api_login(email: str, user_type: str = "student") -> dict[str, Any]:
    """Authenticate student or recruiter by email.

    Args:
        email (str): Registered user email address.
        user_type (str): 'student' or 'recruiter'.

    Returns:
        dict[str, Any]: API response payload with user object and session token.
    """
    payload = {
        "email": email.strip(),
        "user_type": user_type.lower().strip(),
    }
    with _build_client() as client:
        response = client.post("/api/login", json=payload)
        if response.status_code == 200:
            return response.json()
        error_detail = response.json().get("detail", "Login failed. User not found.")
        raise ValueError(error_detail)


def api_register_student(
    name: str,
    email: str,
    github_username: str,
    repo_url: str | None = None,
) -> dict[str, Any]:
    """Register a new student and optionally enqueue initial repository scan.

    Args:
        name (str): Student full name.
        email (str): Student email.
        github_username (str): GitHub handle.
        repo_url (str | None): Optional initial project repository URL.

    Returns:
        dict[str, Any]: Created student and project response.
    """
    payload: dict[str, Any] = {
        "name": name.strip(),
        "email": email.strip(),
        "github_username": github_username.strip(),
    }
    if repo_url and repo_url.strip():
        payload["repo_url"] = repo_url.strip()

    with _build_client() as client:
        response = client.post("/api/register", json=payload)
        if response.status_code in (200, 201):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Registration failed.")
        raise ValueError(detail)


def api_register_recruiter(
    name: str,
    email: str,
    preferred_channel: str = "email",
    telegram_handle: str | None = None,
    preference_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register a new recruiter with notification preferences.

    Args:
        name (str): Recruiter name.
        email (str): Contact work email.
        preferred_channel (str): 'email' or 'telegram'.
        telegram_handle (str | None): Telegram handle if channel is telegram.
        preference_filters (dict[str, Any] | None): Initial matching filters.

    Returns:
        dict[str, Any]: Created recruiter profile record.
    """
    payload: dict[str, Any] = {
        "name": name.strip(),
        "email": email.strip(),
        "preferred_channel": preferred_channel.lower(),
        "preference_filters": preference_filters or {},
    }
    if telegram_handle and telegram_handle.strip():
        payload["telegram_handle"] = telegram_handle.strip()

    with _build_client() as client:
        response = client.post("/api/recruiter/register", json=payload)
        if response.status_code in (200, 201):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Recruiter registration failed.")
        raise ValueError(detail)


# ==========================================
# 2. FEED & DISCOVERY
# ==========================================


@st.cache_data(ttl=30, show_spinner=False)
def fetch_feed(
    page: int = 1,
    limit: int = 10,
    search_query: str | None = None,
    tag: str | None = None,
    min_score: float | None = None,
    preview: bool = False,
) -> dict[str, Any]:
    """Fetch paginated project feed with filters.

    Args:
        page (int): Page number.
        limit (int): Items per page.
        search_query (str | None): Keyword search.
        tag (str | None): Tech stack tag filter.
        min_score (float | None): Minimum final score threshold.
        preview (bool): Whether preview mode is requested.

    Returns:
        dict[str, Any]: Paginated dictionary with projects, total, page, limit.
    """
    params: dict[str, Any] = {
        "page": page,
        "limit": limit,
        "preview": preview,
    }
    if search_query and search_query.strip():
        params["search_query"] = search_query.strip()
    if tag and tag.strip():
        params["tag"] = tag.strip()
    if min_score is not None and min_score > 0:
        params["min_score"] = float(min_score)

    with _build_client() as client:
        response = client.get("/api/dashboard", params=params)
        if response.status_code == 200:
            return response.json()
        return {"items": [], "total": 0, "page": page, "limit": limit}


# ==========================================
# 3. STUDENT & PERSONAL ANALYTICS
# ==========================================


@st.cache_data(ttl=20, show_spinner=False)
def fetch_student_profile(student_id: int) -> dict[str, Any]:
    """Fetch student profile and project portfolio.

    Args:
        student_id (int): Student database ID.

    Returns:
        dict[str, Any]: Profile dictionary containing student, projects, and aggregate_stats.
    """
    with _build_client() as client:
        response = client.get(f"/api/student/{student_id}")
        if response.status_code == 200:
            return response.json()
        detail = response.json().get("detail", f"Student #{student_id} not found")
        raise ValueError(detail)


@st.cache_data(ttl=20, show_spinner=False)
def fetch_project_detail(project_id: int) -> dict[str, Any]:
    """Fetch public project details including metric breakdown and suggestions.

    Args:
        project_id (int): Project database ID.

    Returns:
        dict[str, Any]: Detailed project bundle dictionary.
    """
    with _build_client() as client:
        response = client.get(f"/api/project/{project_id}")
        if response.status_code == 200:
            return response.json()
        raise ValueError(f"Project #{project_id} not found")


@st.cache_data(ttl=20, show_spinner=False)
def fetch_project_analytics(project_id: int) -> dict[str, Any]:
    """Fetch comprehensive Personal Analytics bundle for a project.

    Args:
        project_id (int): Project database ID.

    Returns:
        dict[str, Any]: Structured analytics dashboard payload.
    """
    with _build_client() as client:
        response = client.get(f"/api/project/{project_id}/analytics")
        if response.status_code == 200:
            return response.json()
        raise ValueError(f"Analytics for project #{project_id} not available")


@st.cache_data(ttl=20, show_spinner=False)
def fetch_project_ratings(project_id: int) -> dict[str, Any]:
    """Fetch timestamped ratings history for a project.

    Args:
        project_id (int): Project database ID.

    Returns:
        dict[str, Any]: Ratings list and aggregate summary.
    """
    with _build_client() as client:
        response = client.get(f"/api/project/{project_id}/ratings")
        if response.status_code == 200:
            return response.json()
        return {"project_id": project_id, "ratings": [], "total_ratings": 0, "average_rating": 0.0}


@st.cache_data(ttl=20, show_spinner=False)
def fetch_project_commits(project_id: int, limit: int = 50) -> dict[str, Any]:
    """Fetch commit logs and change classifications for a project.

    Args:
        project_id (int): Project database ID.
        limit (int): Maximum commit count.

    Returns:
        dict[str, Any]: Commits array and total count.
    """
    with _build_client() as client:
        response = client.get(f"/api/project/{project_id}/commits", params={"limit": limit})
        if response.status_code == 200:
            return response.json()
        return {"project_id": project_id, "commits": [], "total_commits": 0}


@st.cache_data(ttl=20, show_spinner=False)
def fetch_project_suggestions(project_id: int) -> dict[str, Any]:
    """Fetch recruiter suggestions for a project.

    Args:
        project_id (int): Project database ID.

    Returns:
        dict[str, Any]: List of recruiter suggestions.
    """
    with _build_client() as client:
        response = client.get(f"/api/project/{project_id}/suggestions")
        if response.status_code == 200:
            return response.json()
        return {"project_id": project_id, "suggestions": [], "total_count": 0}


@st.cache_data(ttl=20, show_spinner=False)
def fetch_project_peer_suggestions(project_id: int) -> dict[str, Any]:
    """Fetch peer community feedback for a project.

    Args:
        project_id (int): Project database ID.

    Returns:
        dict[str, Any]: List of peer feedback comments.
    """
    with _build_client() as client:
        response = client.get(f"/api/project/{project_id}/peer-suggestions")
        if response.status_code == 200:
            return response.json()
        return {"project_id": project_id, "peer_suggestions": [], "total_count": 0}


def api_rate_project(
    project_id: int,
    rating: int,
    rater_type: str = "public",
    rater_id: int | None = None,
) -> dict[str, Any]:
    """Submit a 1-10 rating for a project.

    Args:
        project_id (int): Target project ID.
        rating (int): Integer rating value from 1 to 10.
        rater_type (str): 'public' or 'recruiter'.
        rater_id (int | None): Optional user ID.

    Returns:
        dict[str, Any]: Submission result and new composite score.
    """
    payload = {
        "project_id": project_id,
        "rating": rating,
        "rater_type": rater_type,
        "rater_id": rater_id,
    }
    with _build_client() as client:
        response = client.post("/api/rate", json=payload)
        if response.status_code in (200, 201):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Rating submission failed.")
        raise ValueError(detail)


def api_submit_peer_suggestion(
    project_id: int,
    student_id: int | None,
    student_name: str,
    feedback_text: str,
) -> dict[str, Any]:
    """Submit constructive peer commentary on a project.

    Args:
        project_id (int): Project ID.
        student_id (int | None): Optional commenter ID.
        student_name (str): Commenter display name.
        feedback_text (str): Constructive feedback message.

    Returns:
        dict[str, Any]: Created peer suggestion object.
    """
    payload = {
        "student_id": student_id,
        "student_name": student_name.strip() or "Anonymous Peer",
        "feedback_text": feedback_text.strip(),
    }
    with _build_client() as client:
        response = client.post(f"/api/project/{project_id}/peer-suggestions", json=payload)
        if response.status_code in (200, 201):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Feedback submission failed.")
        raise ValueError(detail)


def api_add_project(student_id: int, repo_url: str) -> dict[str, Any]:
    """Submit a new GitHub repository under an existing student profile.

    Args:
        student_id (int): Registered student ID.
        repo_url (str): GitHub repository URL.

    Returns:
        dict[str, Any]: Created project record.
    """
    payload = {
        "student_id": student_id,
        "repo_url": repo_url.strip(),
    }
    with _build_client() as client:
        response = client.post("/api/projects", json=payload)
        if response.status_code in (200, 201):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Failed to add project.")
        raise ValueError(detail)


# ==========================================
# 4. RECRUITER WORKSPACE & CART
# ==========================================


@st.cache_data(ttl=20, show_spinner=False)
def fetch_recruiter_profile(recruiter_id: int) -> dict[str, Any]:
    """Fetch recruiter profile and pre-matched candidates.

    Args:
        recruiter_id (int): Recruiter ID.

    Returns:
        dict[str, Any]: Recruiter details and matching_projects list.
    """
    with _build_client() as client:
        response = client.get(f"/api/recruiter/{recruiter_id}")
        if response.status_code == 200:
            return response.json()
        raise ValueError(f"Recruiter #{recruiter_id} not found")


@st.cache_data(ttl=20, show_spinner=False)
def fetch_recruiter_suggestions(recruiter_id: int) -> dict[str, Any]:
    """Fetch history of suggestions submitted by a recruiter.

    Args:
        recruiter_id (int): Recruiter ID.

    Returns:
        dict[str, Any]: List of submitted suggestions and status.
    """
    with _build_client() as client:
        response = client.get(f"/api/recruiter/{recruiter_id}/suggestions")
        if response.status_code == 200:
            return response.json()
        return {"recruiter_id": recruiter_id, "suggestions": [], "total_count": 0}


@st.cache_data(ttl=20, show_spinner=False)
def fetch_recruiter_cart(recruiter_id: int) -> dict[str, Any]:
    """Fetch recruiter's saved shortlist cart.

    Args:
        recruiter_id (int): Recruiter ID.

    Returns:
        dict[str, Any]: Cart items list and total count.
    """
    with _build_client() as client:
        response = client.get(f"/api/cart/{recruiter_id}")
        if response.status_code == 200:
            return response.json()
        return {"recruiter_id": recruiter_id, "cart_items": [], "total_count": 0}


def api_add_to_cart(recruiter_id: int, project_id: int) -> dict[str, Any]:
    """Add candidate project to recruiter's shortlist cart.

    Args:
        recruiter_id (int): Recruiter ID.
        project_id (int): Project ID.

    Returns:
        dict[str, Any]: Confirmation result.
    """
    payload = {
        "recruiter_id": recruiter_id,
        "project_id": project_id,
    }
    with _build_client() as client:
        response = client.post("/api/cart", json=payload)
        if response.status_code in (200, 201):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Failed to add candidate to cart.")
        raise ValueError(detail)


def api_remove_from_cart_by_item(item_id: int) -> dict[str, Any]:
    """Remove candidate from cart by cart item ID.

    Args:
        item_id (int): Cart item ID.

    Returns:
        dict[str, Any]: Deletion confirmation.
    """
    with _build_client() as client:
        response = client.delete(f"/api/cart/{item_id}")
        if response.status_code == 200:
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Failed to remove item from cart.")
        raise ValueError(detail)


def api_remove_from_cart(recruiter_id: int, project_id: int) -> dict[str, Any]:
    """Remove candidate from cart by recruiter ID and project ID.

    Args:
        recruiter_id (int): Recruiter ID.
        project_id (int): Project ID.

    Returns:
        dict[str, Any]: Deletion confirmation.
    """
    with _build_client() as client:
        response = client.delete(f"/api/cart/{recruiter_id}/{project_id}")
        if response.status_code == 200:
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Failed to remove project from cart.")
        raise ValueError(detail)


def api_submit_suggestion(
    project_id: int,
    recruiter_id: int,
    suggestion_text: str,
) -> dict[str, Any]:
    """Submit formal recruiter feedback/suggestion on candidate project.

    Args:
        project_id (int): Project ID.
        recruiter_id (int): Recruiter ID.
        suggestion_text (str): Constructive suggestion note.

    Returns:
        dict[str, Any]: Created suggestion record.
    """
    payload = {
        "project_id": project_id,
        "recruiter_id": recruiter_id,
        "suggestion_text": suggestion_text.strip(),
    }
    with _build_client() as client:
        response = client.post("/api/suggest", json=payload)
        if response.status_code in (200, 201):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Failed to submit suggestion.")
        raise ValueError(detail)


def api_update_recruiter_preferences(
    recruiter_id: int,
    preference_filters: dict[str, Any],
) -> dict[str, Any]:
    """Update hiring preference filters for a recruiter.

    Args:
        recruiter_id (int): Recruiter ID.
        preference_filters (dict[str, Any]): Updated filter criteria.

    Returns:
        dict[str, Any]: Updated recruiter record.
    """
    payload = {"preference_filters": preference_filters}
    with _build_client() as client:
        response = client.patch(f"/api/recruiter/{recruiter_id}/preferences", json=payload)
        if response.status_code == 200:
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Failed to update preferences.")
        raise ValueError(detail)


# ==========================================
# 5. ADMIN & WEBHOOK SIMULATION
# ==========================================


def api_admin_scan(
    project_id: int | None = None,
    admin_key: str | None = None,
) -> dict[str, Any]:
    """Trigger background AI repository re-scan.

    Args:
        project_id (int | None): Optional specific project ID.
        admin_key (str | None): Admin API key.

    Returns:
        dict[str, Any]: Queued status response.
    """
    key = admin_key or get_admin_api_key()
    headers = {"X-Admin-API-Key": key}
    payload = {"project_id": project_id}
    with _build_client() as client:
        response = client.post("/api/admin/scan", json=payload, headers=headers)
        if response.status_code in (200, 202):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", "Admin scan failed.")
        raise ValueError(detail)


def api_admin_notify(
    project_id: int,
    recruiter_id: int | None = None,
    admin_key: str | None = None,
) -> dict[str, Any]:
    """Trigger multi-channel recruiter Telegram/email notifications.

    Args:
        project_id (int): Target project ID.
        recruiter_id (int | None): Optional single recruiter ID.
        admin_key (str | None): Admin API key.

    Returns:
        dict[str, Any]: Queued status response.
    """
    key = admin_key or get_admin_api_key()
    headers = {"X-Admin-API-Key": key}
    payload = {"project_id": project_id, "recruiter_id": recruiter_id}
    with _build_client() as client:
        response = client.post("/api/admin/notify", json=payload, headers=headers)
        if response.status_code in (200, 202):
            return response.json()
        detail = response.json().get("detail", "Admin notification dispatch failed.")
        raise ValueError(detail)


def api_trigger_webhook(
    payload: dict[str, Any],
    event: str = "push",
    delivery_id: str | None = None,
    secret: str = "skip_signature_verification",
) -> dict[str, Any]:
    """Simulate GitHub Webhook event dispatch to backend.

    Args:
        payload (dict[str, Any]): GitHub webhook JSON payload.
        event (str): Event name ('push').
        delivery_id (str | None): Optional unique delivery UUID.
        secret (str): Webhook secret or 'skip_signature_verification'.

    Returns:
        dict[str, Any]: Webhook endpoint response.
    """
    body_bytes = json.dumps(payload).encode("utf-8")
    headers: dict[str, str] = {
        "X-GitHub-Event": event,
        "Content-Type": "application/json",
    }
    if delivery_id:
        headers["X-GitHub-Delivery"] = delivery_id

    if secret != "skip_signature_verification":
        sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={sig}"

    with _build_client() as client:
        response = client.post("/api/webhook/github", content=body_bytes, headers=headers)
        if response.status_code in (200, 202):
            clear_api_cache()
            return response.json()
        detail = response.json().get("detail", f"Webhook failed with status {response.status_code}")
        raise ValueError(detail)
