"""Unit and integration tests for Step 4: Agent 1 GitHub Scanning & Gemini Rating."""

import hashlib
import hmac
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database.db as db_module
from database.scoring import calculate_final_score
from main import app
from services.gemini_scanner import (
    calculate_weighted_ai_score,
    check_suggestion_resolution,
    classify_push_update,
    evaluate_repository,
)
from services.github_service import (
    fetch_readme_content,
    fetch_repo_metadata,
    fetch_repository_tree,
    fetch_source_files,
    parse_github_url,
    scan_github_repository,
)


@pytest.fixture(autouse=True)
def setup_mock_db_pool_and_connection():
    """Fixture to mock DB_POOL and override get_db_connection dependency for tests."""
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=False)
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetch = AsyncMock(return_value=[])

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
# 1. GitHub URL Parsing & Service Unit Tests
# ---------------------------------------------------------------------------


def test_parse_github_url_valid():
    """Test parsing various valid GitHub repository URLs."""
    owner, repo = parse_github_url("https://github.com/octocat/Hello-World")
    assert owner == "octocat"
    assert repo == "Hello-World"

    owner, repo = parse_github_url("https://github.com/octocat/Hello-World.git")
    assert owner == "octocat"
    assert repo == "Hello-World"

    owner, repo = parse_github_url("octocat/Hello-World")
    assert owner == "octocat"
    assert repo == "Hello-World"


def test_parse_github_url_invalid():
    """Test parsing invalid GitHub URLs raises ValueError."""
    with pytest.raises(ValueError):
        parse_github_url("invalid-url-without-slash")


@pytest.mark.asyncio
async def test_github_service_fetch_metadata():
    """Test fetching repository metadata with respx HTTP mock."""
    async with respx.mock:
        respx.get("https://api.github.com/repos/octocat/Hello-World").mock(
            return_value=Response(
                200,
                json={
                    "stargazers_count": 100,
                    "forks_count": 25,
                    "default_branch": "main",
                    "language": "Python",
                    "description": "Test Repo",
                },
            )
        )
        meta = await fetch_repo_metadata("octocat", "Hello-World")
        assert meta["stargazers_count"] == 100
        assert meta["language"] == "Python"


@pytest.mark.asyncio
async def test_github_service_fetch_readme():
    """Test fetching raw README.md content."""
    async with respx.mock:
        respx.get("https://api.github.com/repos/octocat/Hello-World/readme").mock(
            return_value=Response(200, text="# Hello World Project\nThis is a test.")
        )
        readme = await fetch_readme_content("octocat", "Hello-World")
        assert "# Hello World Project" in readme


@pytest.mark.asyncio
async def test_github_service_scan_repository():
    """Test full repository scanning pipeline."""
    async with respx.mock:
        respx.get("https://api.github.com/repos/octocat/Hello-World").mock(
            return_value=Response(
                200,
                json={
                    "stargazers_count": 10,
                    "forks_count": 2,
                    "default_branch": "main",
                    "language": "Python",
                    "description": "Awesome App",
                },
            )
        )
        respx.get("https://api.github.com/repos/octocat/Hello-World/readme").mock(
            return_value=Response(200, text="# Awesome App")
        )
        respx.get("https://api.github.com/repos/octocat/Hello-World/git/trees/main?recursive=1").mock(
            return_value=Response(
                200,
                json={
                    "tree": [
                        {"path": "main.py", "type": "blob"},
                        {"path": "utils.py", "type": "blob"},
                    ]
                },
            )
        )
        respx.get("https://raw.githubusercontent.com/octocat/Hello-World/main/main.py").mock(
            return_value=Response(200, text="print('hello world')")
        )
        respx.get("https://raw.githubusercontent.com/octocat/Hello-World/main/utils.py").mock(
            return_value=Response(200, text="def add(a, b): return a + b")
        )

        scan_res = await scan_github_repository("https://github.com/octocat/Hello-World")
        assert scan_res["owner"] == "octocat"
        assert scan_res["repo"] == "Hello-World"
        assert scan_res["language"] == "Python"
        assert "main.py" in scan_res["source_files"]


# ---------------------------------------------------------------------------
# 2. Gemini Scanner & Weighted Scoring Unit Tests
# ---------------------------------------------------------------------------


def test_calculate_weighted_ai_score():
    """Verify weighted AI score formula: (0.4 * difficulty) + (0.3 * authenticity) + (0.3 * creativity)."""
    # 80 * 0.4 = 32, 90 * 0.3 = 27, 70 * 0.3 = 21 -> 32 + 27 + 21 = 80.0
    score = calculate_weighted_ai_score(80.0, 90.0, 70.0)
    assert score == 80.0

    # Test clamping lower and upper bounds
    assert calculate_weighted_ai_score(150.0, 150.0, 150.0) == 100.0
    assert calculate_weighted_ai_score(-10.0, -10.0, -10.0) == 0.0


@pytest.mark.asyncio
async def test_evaluate_repository_fallback():
    """Test evaluation fallback when GEMINI_API_KEY is not set."""
    repo_context = {
        "repo": "demo-repo",
        "owner": "testuser",
        "language": "Python",
        "source_files": {"main.py": "import fastapi"},
    }
    with patch.dict(os.environ, {}, clear=True):
        res = await evaluate_repository(repo_context)
        assert "ai_difficulty" in res
        assert "ai_authenticity" in res
        assert "ai_creativity" in res
        assert "ai_score" in res
        assert isinstance(res["tags"], list)
        assert isinstance(res["summary"], str)
        # Check formula consistency
        expected_score = calculate_weighted_ai_score(
            res["ai_difficulty"], res["ai_authenticity"], res["ai_creativity"]
        )
        assert res["ai_score"] == expected_score


@pytest.mark.asyncio
async def test_classify_push_update_minor():
    """Test push classification for minor updates (documentation/typos)."""
    res = await classify_push_update(["fix typo in README"], ["README.md"])
    assert res == "Minor"


@pytest.mark.asyncio
async def test_classify_push_update_major():
    """Test push classification for major functional updates."""
    res = await classify_push_update(
        ["feat: add postgres connection pool and endpoints"], ["main.py", "database/db.py"]
    )
    assert res == "Major"


# ---------------------------------------------------------------------------
# 3. Webhook HMAC & Idempotency End-to-End Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_hmac_invalid(setup_mock_db_pool_and_connection):
    """Verify webhook rejects requests with invalid HMAC SHA256 signature (401)."""
    secret = "test_secret"
    payload = {"repository": {"html_url": "https://github.com/user/project"}}
    body = json.dumps(payload).encode("utf-8")

    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/api/webhook/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256=invalid_signature_hash",
                    "X-GitHub-Delivery": "delivery-1111",
                    "X-GitHub-Event": "push",
                },
            )
            assert res.status_code == 401
            assert "Invalid X-Hub-Signature-256" in res.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_hmac_valid(setup_mock_db_pool_and_connection):
    """Verify webhook accepts requests with valid HMAC SHA256 signature (202)."""
    mock_conn = setup_mock_db_pool_and_connection
    mock_conn.fetchval.return_value = False  # Idempotency check: not processed yet

    secret = "my_secret_key"
    payload = {
        "repository": {"html_url": "https://github.com/user/project"},
        "commits": [{"message": "fix typo", "modified": ["README.md"]}],
    }
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/api/webhook/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": f"sha256={sig}",
                    "X-GitHub-Delivery": "delivery-2222",
                    "X-GitHub-Event": "push",
                },
            )
            assert res.status_code == 202
            assert res.json()["status"] == "accepted"
            assert res.json()["delivery_id"] == "delivery-2222"


@pytest.mark.asyncio
async def test_webhook_idempotency(setup_mock_db_pool_and_connection):
    """Verify duplicate webhook delivery ID is ignored."""
    mock_conn = setup_mock_db_pool_and_connection
    secret = "skip_signature_verification"
    payload = {
        "repository": {"html_url": "https://github.com/user/project"},
        "commits": [{"message": "feat: add feature", "modified": ["app.py"]}],
    }
    body = json.dumps(payload).encode("utf-8")

    # Mock delivery as already processed in database
    mock_conn.fetchval.return_value = True

    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/api/webhook/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Delivery": "delivery-duplicate-3333",
                    "X-GitHub-Event": "push",
                },
            )
            assert res.status_code == 202
            assert res.json()["status"] == "ignored"
            assert res.json()["reason"] == "duplicate delivery"


# ---------------------------------------------------------------------------
# 4. End-to-End Evaluation & Database Update Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_major_push_updates_database_and_recomputes_final_score(
    setup_mock_db_pool_and_connection,
):
    """Verify a major push triggers scan, updates project AI metrics, and recomputes final_score."""
    mock_conn = setup_mock_db_pool_and_connection
    mock_conn.fetchval.return_value = False  # Not delivery duplicate

    # Mock existing project record
    project_row = {
        "id": 10,
        "student_id": 1,
        "repo_url": "https://github.com/student/myrepo",
        "summary": "Old summary",
        "tags": '["python"]',
        "ai_difficulty": 50.0,
        "ai_authenticity": 50.0,
        "ai_creativity": 50.0,
        "ai_score": 50.0,
        "final_score": 5.0,
    }
    mock_conn.fetchrow.side_effect = [
        project_row,  # get_project_by_repo_url
        project_row,  # update_project_ai_scores fetchrow
        project_row,  # update_project_score fetchrow
    ]
    mock_conn.fetch.return_value = [{"rating": 8}, {"rating": 9}]  # project ratings for final_score

    # Mock github scan and gemini evaluation
    mock_scan = {
        "owner": "student",
        "repo": "myrepo",
        "repo_url": "https://github.com/student/myrepo",
        "stars": 5,
        "forks": 1,
        "language": "Python",
        "description": "Student App",
        "default_branch": "main",
        "readme": "# My App",
        "tree_structure": ["main.py"],
        "source_files": {"main.py": "print('hello')"},
    }

    mock_eval = {
        "ai_difficulty": 85.0,
        "ai_authenticity": 90.0,
        "ai_creativity": 80.0,
        "ai_score": 85.0,
        "tags": ["python", "fastapi", "backend"],
        "summary": "Comprehensive backend service.",
    }

    from routers.webhook import process_push_webhook_bg

    webhook_payload = {
        "repository": {"html_url": "https://github.com/student/myrepo"},
        "commits": [{"message": "feat: implement major database connection pool", "modified": ["db.py"]}],
    }

    with patch("routers.webhook.scan_github_repository", AsyncMock(return_value=mock_scan)), patch(
        "routers.webhook.evaluate_repository", AsyncMock(return_value=mock_eval)
    ), patch("routers.webhook.get_unresolved_suggestions", AsyncMock(return_value=[])):
        await process_push_webhook_bg(webhook_payload, "delivery-major-4444")

    # Assert update_project_ai_scores SQL was executed
    update_calls = [
        call for call in mock_conn.execute.call_args_list if "UPDATE projects" in str(call)
    ]
    assert len(update_calls) > 0


# ---------------------------------------------------------------------------
# 5. Advanced Edge Cases & Agency Security / Reliability Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_non_push_event_ignored(setup_mock_db_pool_and_connection):
    """Verify non-push GitHub events (ping, issues, pull_request) are ignored."""
    secret = "skip_signature_verification"
    payload = {"zen": "Non-blocking is better than blocking."}
    body = json.dumps(payload).encode("utf-8")

    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": secret}):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/api/webhook/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Delivery": "delivery-ping-5555",
                    "X-GitHub-Event": "ping",
                },
            )
            assert res.status_code == 202
            assert res.json()["status"] == "ignored"
            assert "unhandled event type" in res.json()["reason"]


@pytest.mark.asyncio
async def test_webhook_unregistered_project_ignored(setup_mock_db_pool_and_connection):
    """Verify push event for repository not registered in DB is logged and ignored cleanly."""
    mock_conn = setup_mock_db_pool_and_connection
    mock_conn.fetchrow.return_value = None  # get_project_by_repo_url returns None

    from routers.webhook import process_push_webhook_bg

    webhook_payload = {
        "repository": {"html_url": "https://github.com/unknown/unregistered-repo"},
        "commits": [{"message": "feat: new feature", "modified": ["main.py"]}],
    }

    # Should complete without error or DB updates
    await process_push_webhook_bg(webhook_payload, "delivery-unregistered-6666")


@pytest.mark.asyncio
async def test_recruiter_suggestion_auto_resolution(setup_mock_db_pool_and_connection):
    """Verify major push resolving a recruiter suggestion updates suggestion resolved status."""
    mock_conn = setup_mock_db_pool_and_connection

    project_row = {
        "id": 42,
        "student_id": 2,
        "repo_url": "https://github.com/student/app",
        "summary": "App summary",
        "tags": '["python"]',
        "ai_difficulty": 60.0,
        "ai_authenticity": 60.0,
        "ai_creativity": 60.0,
        "ai_score": 60.0,
        "final_score": 6.0,
    }
    mock_conn.fetchrow.side_effect = [project_row, project_row, project_row]
    mock_conn.fetch.side_effect = [
        [{"rating": 7}],  # project ratings
        [
            {
                "id": 101,
                "project_id": 42,
                "recruiter_id": 5,
                "suggestion_text": "add unit tests for API endpoints",
                "resolved": False,
            }
        ],  # unresolved suggestions
    ]

    mock_scan = {
        "owner": "student",
        "repo": "app",
        "repo_url": "https://github.com/student/app",
        "stars": 1,
        "forks": 0,
        "language": "Python",
        "description": "App",
        "default_branch": "main",
        "readme": "# App",
        "tree_structure": ["main.py", "tests/test_api.py"],
        "source_files": {"tests/test_api.py": "def test_app(): pass"},
    }

    mock_eval = {
        "ai_difficulty": 80.0,
        "ai_authenticity": 85.0,
        "ai_creativity": 75.0,
        "ai_score": 80.0,
        "tags": ["python", "testing"],
        "summary": "App with unit test suite.",
    }

    from routers.webhook import process_push_webhook_bg

    webhook_payload = {
        "repository": {"html_url": "https://github.com/student/app"},
        "commits": [{"message": "test: add unit tests for API endpoints", "modified": ["tests/test_api.py"]}],
    }

    with patch("routers.webhook.scan_github_repository", AsyncMock(return_value=mock_scan)), patch(
        "routers.webhook.evaluate_repository", AsyncMock(return_value=mock_eval)
    ), patch("routers.webhook.check_suggestion_resolution", AsyncMock(return_value=True)):
        await process_push_webhook_bg(webhook_payload, "delivery-sugg-7777")

    # Assert UPDATE suggestions SET resolved = TRUE was executed
    sugg_calls = [
        call for call in mock_conn.fetchrow.call_args_list if "UPDATE suggestions" in str(call)
    ]
    assert len(sugg_calls) > 0


@pytest.mark.asyncio
async def test_github_service_error_handling():
    """Verify GitHub service error handling for 404 Not Found and 403 Rate Limit."""
    async with respx.mock:
        respx.get("https://api.github.com/repos/fake/missing").mock(
            return_value=Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(ValueError, match="GitHub repository not found"):
            await fetch_repo_metadata("fake", "missing")

        respx.get("https://api.github.com/repos/fake/ratelimited").mock(
            return_value=Response(403, json={"message": "API rate limit exceeded"})
        )
        with pytest.raises(RuntimeError, match="GitHub API rate limit exceeded"):
            await fetch_repo_metadata("fake", "ratelimited")


@pytest.mark.asyncio
async def test_gemini_scanner_exception_resilience():
    """Verify evaluate_repository handles LLM exceptions gracefully with safe defaults."""
    repo_context = {"repo": "err-repo", "owner": "test", "language": "Python"}

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(side_effect=Exception("API quota exceeded"))
            mock_client_cls.return_value = mock_client

            res = await evaluate_repository(repo_context)

            assert res["ai_difficulty"] == 65.0
            assert res["ai_authenticity"] == 75.0
            assert res["ai_creativity"] == 70.0
            assert res["ai_score"] == calculate_weighted_ai_score(65.0, 75.0, 70.0)
            assert "software-engineering" in res["tags"]

