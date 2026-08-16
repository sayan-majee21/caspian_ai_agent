"""Comprehensive Round-Trip Routing and Navigation Audit Test Suite."""

import re
from pathlib import Path
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from main import app
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
    get_backend_url,
)


@pytest.fixture
def test_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


class TestFastAPIRouteDefinitions:
    """Validate that every registered route in the FastAPI application schema exists and is reachable."""

    @pytest.mark.asyncio
    async def test_all_route_endpoints_exist(self, test_client):
        openapi_schema = app.openapi()
        routes = list(openapi_schema["paths"].keys())
        for r in app.routes:
            if hasattr(r, "path") and r.path not in routes:
                routes.append(r.path)

        expected_routes = [
            "/",
            "/health",
            "/api/register",
            "/api/dashboard",
            "/api/feed",
            "/api/rate",
            "/api/login",
            "/api/auth/login",
            "/api/student/{student_id}",
            "/api/projects",
            "/api/project/{project_id}",
            "/api/project/{project_id}/analytics",
            "/api/project/{project_id}/ratings",
            "/api/project/{project_id}/commits",
            "/api/project/{project_id}/suggestions",
            "/api/project/{project_id}/peer-suggestions",
            "/api/recruiter/register",
            "/api/recruiter/{recruiter_id}",
            "/api/suggest",
            "/api/recruiter/{recruiter_id}/suggestions",
            "/api/recruiter/{recruiter_id}/preferences",
            "/api/cart/{recruiter_id}",
            "/api/cart",
            "/api/cart/{item_id}",
            "/api/cart/{recruiter_id}/{project_id}",
            "/api/admin/scan",
            "/api/admin/notify",
            "/api/webhook",
            "/api/webhook/",
            "/api/webhook/github",
        ]

        for expected in expected_routes:
            assert expected in routes, f"Missing route definition: {expected}"


class TestStreamlitPageNavigationIntegrity:
    """Audit all st.Page and st.switch_page references across frontend files."""

    def test_all_navigation_file_targets_exist(self):
        root = Path(__file__).parent.parent
        pages_dir = root / "pages"
        utils_dir = root / "utils"

        scanned_files = [root / "app.py"] + list(pages_dir.glob("*.py")) + list(utils_dir.glob("*.py"))
        switch_pattern = re.compile(r'st\.(?:switch_page|Page)\(\s*["\']([^"\']+)["\']')

        referenced_pages = set()
        for f in scanned_files:
            content = f.read_text(encoding="utf-8")
            matches = switch_pattern.findall(content)
            for m in matches:
                if m.endswith(".py"):
                    referenced_pages.add(m)

        assert len(referenced_pages) == 8, f"Expected 8 unique pages, found: {len(referenced_pages)}"
        for page_rel_path in referenced_pages:
            target_file = root / page_rel_path
            assert target_file.exists(), f"Navigation target does not exist: {page_rel_path}"


class TestRoundTripApiClientRouting:
    """Verify that all API client functions issue HTTP requests matching backend route specifications."""

    @respx.mock
    def test_all_api_client_routes_roundtrip(self):
        backend_url = get_backend_url()

        # Public & Student routes
        respx.post(f"{backend_url}/api/login").respond(status_code=200, json={"status": "success", "user": {"id": 1}})
        respx.post(f"{backend_url}/api/register").respond(status_code=201, json={"status": "success", "student": {"id": 1}})
        respx.get(f"{backend_url}/api/dashboard").respond(status_code=200, json={"items": [], "total": 0})
        respx.get(f"{backend_url}/api/student/1").respond(status_code=200, json={"student": {"id": 1}})
        respx.get(f"{backend_url}/api/project/1").respond(status_code=200, json={"project": {"id": 1}})
        respx.get(f"{backend_url}/api/project/1/analytics").respond(status_code=200, json={"header": {}})
        respx.get(f"{backend_url}/api/project/1/ratings").respond(status_code=200, json={"ratings": []})
        respx.get(f"{backend_url}/api/project/1/commits").respond(status_code=200, json={"commits": []})
        respx.get(f"{backend_url}/api/project/1/suggestions").respond(status_code=200, json={"suggestions": []})
        respx.get(f"{backend_url}/api/project/1/peer-suggestions").respond(status_code=200, json={"peer_suggestions": []})
        respx.post(f"{backend_url}/api/rate").respond(status_code=201, json={"status": "success"})
        respx.post(f"{backend_url}/api/project/1/peer-suggestions").respond(status_code=201, json={"status": "success"})
        respx.post(f"{backend_url}/api/projects").respond(status_code=201, json={"status": "success"})

        # Recruiter routes
        respx.post(f"{backend_url}/api/recruiter/register").respond(status_code=201, json={"id": 1})
        respx.get(f"{backend_url}/api/recruiter/1").respond(status_code=200, json={"recruiter": {"id": 1}})
        respx.get(f"{backend_url}/api/recruiter/1/suggestions").respond(status_code=200, json={"suggestions": []})
        respx.get(f"{backend_url}/api/cart/1").respond(status_code=200, json={"cart_items": []})
        respx.post(f"{backend_url}/api/cart").respond(status_code=201, json={"status": "success"})
        respx.delete(f"{backend_url}/api/cart/1").respond(status_code=200, json={"status": "success"})
        respx.delete(f"{backend_url}/api/cart/1/10").respond(status_code=200, json={"status": "success"})
        respx.post(f"{backend_url}/api/suggest").respond(status_code=201, json={"status": "success"})
        respx.patch(f"{backend_url}/api/recruiter/1/preferences").respond(status_code=200, json={"status": "success"})

        # Admin & Webhook routes
        respx.post(f"{backend_url}/api/admin/scan").respond(status_code=202, json={"status": "queued"})
        respx.post(f"{backend_url}/api/admin/notify").respond(status_code=202, json={"status": "queued"})
        respx.post(f"{backend_url}/api/webhook/github").respond(status_code=202, json={"status": "accepted"})

        # Execute and assert calls
        assert api_login("test@test.com", "student")["status"] == "success"
        assert api_register_student("A", "a@a.com", "adev")["status"] == "success"
        assert fetch_feed()["total"] == 0
        assert fetch_student_profile(1)["student"]["id"] == 1
        assert fetch_project_detail(1)["project"]["id"] == 1
        assert fetch_project_analytics(1) == {"header": {}}
        assert fetch_project_ratings(1)["ratings"] == []
        assert fetch_project_commits(1)["commits"] == []
        assert fetch_project_suggestions(1)["suggestions"] == []
        assert fetch_project_peer_suggestions(1)["peer_suggestions"] == []
        assert api_rate_project(1, 10)["status"] == "success"
        assert api_submit_peer_suggestion(1, 1, "Peer", "Nice work")["status"] == "success"
        assert api_add_project(1, "https://github.com/a/b")["status"] == "success"

        assert api_register_recruiter("R", "r@r.com")["id"] == 1
        assert fetch_recruiter_profile(1)["recruiter"]["id"] == 1
        assert fetch_recruiter_suggestions(1)["suggestions"] == []
        assert fetch_recruiter_cart(1)["cart_items"] == []
        assert api_add_to_cart(1, 10)["status"] == "success"
        assert api_remove_from_cart_by_item(1)["status"] == "success"
        assert api_remove_from_cart(1, 10)["status"] == "success"
        assert api_submit_suggestion(10, 1, "Good project")["status"] == "success"
        assert api_update_recruiter_preferences(1, {"min_score": 80})["status"] == "success"

        assert api_admin_scan(1)["status"] == "queued"
        assert api_admin_notify(1, 1)["status"] == "queued"
        assert api_trigger_webhook({"repository": {"html_url": "https://github.com/a/b"}})["status"] == "accepted"
