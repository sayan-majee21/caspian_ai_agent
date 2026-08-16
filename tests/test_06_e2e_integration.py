"""Master End-to-End Integration Test Suite for TalentCaspian Platform.

Simulates and verifies the complete lifecycle across all steps (0 through 5):
1. Student & Project Registration (DB & API layer)
2. Community Rating & Bayesian Score Updates
3. Agent 1 GitHub Repository Scanning & Gemini AI Evaluation
4. Recruiter Profile Creation with JSONB Preference Filters & Tag/Score Matching
5. Recruiter Suggestion Feedback & GitHub Push Webhook Auto-Resolution
6. Agent 2 Follow-Up Notification Dispatching & Caspian Multi-Channel Outreach
7. Admin Notification Batch Process Triggering (POST /api/admin/notify)
8. Audit Trail Recording in notification_logs database table
"""

from datetime import datetime
import hashlib
import hmac
import json
import os
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from caspian_sdk import CommClient, Message
import database.db as db_module
from database.db import (
    add_project_rating,
    add_suggestion,
    create_notification_log,
    create_project,
    create_recruiter,
    create_student,
    get_project_by_id,
    get_project_by_repo_url,
    get_recruiter_by_id,
    get_unresolved_suggestions,
    has_recent_notification,
    mark_suggestion_resolved,
    update_project_ai_scores,
    update_project_score,
)
from database.scoring import calculate_bayesian_average, calculate_final_score
from main import app
from services.caspian_outreach import dispatch_message
from services.gemini_scanner import (
    calculate_weighted_ai_score,
    check_suggestion_resolution,
    classify_push_update,
    evaluate_repository,
)
from services.github_service import scan_github_repository
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
# Fixture: Stateful Mock DB Engine for E2E Testing
# ---------------------------------------------------------------------------
class StatefulMockDB:
    """In-memory mock database to simulate asyncpg connection operations realistically."""

    def __init__(self):
        self.students = {}
        self.projects = {}
        self.recruiters = {}
        self.ratings = []
        self.suggestions = {}
        self.notification_logs = []
        self.processed_deliveries = set()
        self.next_student_id = 1
        self.next_project_id = 1
        self.next_recruiter_id = 1
        self.next_suggestion_id = 1
        self.next_log_id = 1

    def acquire(self):
        db_self = self
        class ConnContext:
            async def __aenter__(self):
                return db_self
            async def __aexit__(self, exc_type, exc, tb):
                pass
        return ConnContext()

    def transaction(self):
        class TxContext:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                pass
        return TxContext()

    async def fetchrow(self, query: str, *args):

        q = query.upper()
        if "INSERT INTO STUDENTS" in q:
            student_id = self.next_student_id
            self.next_student_id += 1
            rec = {
                "id": student_id,
                "name": args[0],
                "email": args[1],
                "github_username": args[2],
                "created_at": datetime.now(),
            }
            self.students[student_id] = rec
            return rec

        elif "INSERT INTO PROJECTS" in q:
            project_id = self.next_project_id
            self.next_project_id += 1
            tags = json.loads(args[3]) if isinstance(args[3], str) else (args[3] or [])
            rec = {
                "id": project_id,
                "student_id": args[0],
                "repo_url": args[1],
                "summary": args[2],
                "tags": tags,
                "ai_difficulty": None,
                "ai_authenticity": None,
                "ai_creativity": None,
                "ai_score": None,
                "final_score": args[4],
                "last_scanned_at": None,
                "created_at": datetime.now(),
            }
            self.projects[project_id] = rec
            return rec

        elif "INSERT INTO RECRUITERS" in q:
            recruiter_id = self.next_recruiter_id
            self.next_recruiter_id += 1
            pref = json.loads(args[4]) if isinstance(args[4], str) else (args[4] or {})
            rec = {
                "id": recruiter_id,
                "name": args[0],
                "email": args[1],
                "preferred_channel": args[2],
                "telegram_handle": args[3],
                "preference_filters": pref,
                "created_at": datetime.now(),
            }
            self.recruiters[recruiter_id] = rec
            return rec

        elif "INSERT INTO PROJECT_RATINGS" in q:
            rec = {
                "id": len(self.ratings) + 1,
                "project_id": args[0],
                "rater_type": args[1],
                "rater_id": args[2],
                "rater_ip_hash": args[3],
                "rating": args[4],
                "created_at": datetime.now(),
            }
            self.ratings.append(rec)
            return rec

        elif "INSERT INTO SUGGESTIONS" in q:
            sugg_id = self.next_suggestion_id
            self.next_suggestion_id += 1
            rec = {
                "id": sugg_id,
                "project_id": args[0],
                "recruiter_id": args[1],
                "suggestion_text": args[2],
                "resolved": False,
                "created_at": datetime.now(),
            }
            self.suggestions[sugg_id] = rec
            return rec

        elif "INSERT INTO NOTIFICATION_LOGS" in q:
            log_id = self.next_log_id
            self.next_log_id += 1
            rec = {
                "id": log_id,
                "recruiter_id": args[0],
                "project_id": args[1],
                "channel": args[2],
                "is_followup": args[3],
                "sent_at": datetime.now(),
            }
            self.notification_logs.append(rec)
            return rec

        elif "UPDATE SUGGESTIONS" in q and "SET RESOLVED = TRUE" in q:
            sugg_id = args[0]
            if sugg_id in self.suggestions:
                self.suggestions[sugg_id]["resolved"] = True
                return self.suggestions[sugg_id]
            return None

        elif "SELECT * FROM PROJECTS WHERE ID =" in q or "FROM PROJECTS P" in q and "WHERE P.ID =" in q:
            pid = args[0]
            if pid in self.projects:
                proj = dict(self.projects[pid])
                student = self.students.get(proj["student_id"], {})
                proj["student_name"] = student.get("name")
                proj["github_username"] = student.get("github_username")
                proj["student_email"] = student.get("email")
                return proj
            return None

        elif "FROM RECRUITERS" in q and "WHERE" in q and "ID =" in q:
            rid = args[0]
            return self.recruiters.get(rid)

        elif "FROM RECRUITERS" in q and "LOWER(EMAIL)" in q:
            contact = str(args[0]).strip().lower().lstrip("@")
            for r in self.recruiters.values():
                r_email = r["email"].lower()
                r_tg = (r.get("telegram_handle") or "").lower().lstrip("@")
                if r_email == contact or r_tg == contact:
                    return r
            return None


        elif "FROM PROJECTS" in q and "LOWER(REPO_URL)" in q:
            url = args[0].lower()
            for proj in self.projects.values():
                if proj["repo_url"].lower() in url or url in proj["repo_url"].lower():
                    return dict(proj)
            return None

        elif "SELECT AI_SCORE FROM PROJECTS" in q:
            pid = args[0]
            proj = self.projects.get(pid)
            return proj.get("ai_score") if proj else None

        return None

    async def fetch(self, query: str, *args):
        q = query.upper()
        if "SELECT RATING FROM PROJECT_RATINGS WHERE PROJECT_ID =" in q:
            pid = args[0]
            return [{"rating": r["rating"]} for r in self.ratings if r["project_id"] == pid]

        elif "WHERE P.ID = $1" in q and ("RECRUITERS" in q or "PROJECTS" in q):
            pid = args[0]
            proj = self.projects.get(pid)
            if not proj:
                return []
            p_score = proj.get("final_score")
            if p_score is None:
                p_score = proj.get("ai_score") or 80.0
            p_tags = set(proj.get("tags") or [])
            matched = []
            for r in self.recruiters.values():
                filters = r.get("preference_filters") or {}
                min_s = filters.get("min_score", 0.0)
                req_tags = set(filters.get("tech_stack") or [])
                if p_score >= min_s:
                    if not req_tags or bool(p_tags.intersection(req_tags)):
                        matched.append(r)
            return matched

        elif "WHERE R.ID = $1" in q:
            rid = args[0]
            rec = self.recruiters.get(rid)
            if not rec:
                return []
            filters = rec.get("preference_filters") or {}
            min_s = filters.get("min_score", 0.0)
            req_tags = set(filters.get("tech_stack") or [])
            matched = []
            for pid, proj in self.projects.items():
                student = self.students.get(proj["student_id"], {})
                p_score = proj.get("final_score")
                if p_score is None:
                    p_score = proj.get("ai_score") or 80.0
                p_tags = set(proj.get("tags") or [])
                if p_score >= min_s:
                    if not req_tags or bool(p_tags.intersection(req_tags)):
                        matched.append({
                            **proj,
                            "student_name": student.get("name"),
                            "github_username": student.get("github_username"),
                            "student_email": student.get("email"),
                        })
            return matched



        elif "FROM SUGGESTIONS" in q and "PROJECT_ID =" in q:
            pid = int(args[0])
            return [
                dict(s)
                for s in self.suggestions.values()
                if int(s["project_id"]) == pid and not s.get("resolved")
            ]

        elif "JOIN STUDENTS" in q or "FROM PROJECTS" in q:
            items = []
            for pid, proj in self.projects.items():
                student = self.students.get(proj["student_id"], {})
                f_score = proj.get("final_score")
                if f_score is None:
                    f_score = proj.get("ai_score") or 75.0
                items.append(
                    {
                        **proj,
                        "final_score": f_score,
                        "summary": proj.get("summary") or "Project summary",
                        "student_name": student.get("name"),
                        "github_username": student.get("github_username"),
                        "student_email": student.get("email"),
                        "ratings_count": len([r for r in self.ratings if r["project_id"] == pid]),
                    }
                )
            items.sort(key=lambda x: (x.get("final_score") or 0.0), reverse=True)
            return items


        return []

    async def fetchval(self, query: str, *args):
        q = query.upper()
        if "SELECT PROJECT_ID" in q and "NOTIFICATION_LOGS" in q:
            rid = args[0]
            for l in reversed(self.notification_logs):
                if l["recruiter_id"] == rid:
                    return l["project_id"]
            return None
        elif "SELECT EXISTS" in q and "NOTIFICATION_LOGS" in q:
            rid, pid = args[0], args[1]
            return any(
                l["recruiter_id"] == rid and l["project_id"] == pid for l in self.notification_logs
            )
        elif "SELECT EXISTS" in q and "PROCESSED_DELIVERIES" in q:
            return args[0] in self.processed_deliveries
        elif "SELECT COUNT(*)" in q:
            return len(self.projects)
        elif "SELECT AI_SCORE" in q:
            pid = args[0]
            proj = self.projects.get(pid)
            return proj.get("ai_score") if proj else None
        return False

    async def execute(self, query: str, *args):
        q = query.upper()
        if "AI_DIFFICULTY" in q:
            pid = args[6]
            if pid in self.projects:
                self.projects[pid]["ai_difficulty"] = args[0]
                self.projects[pid]["ai_authenticity"] = args[1]
                self.projects[pid]["ai_creativity"] = args[2]
                self.projects[pid]["ai_score"] = args[3]
                self.projects[pid]["tags"] = json.loads(args[4]) if isinstance(args[4], str) else args[4]
                self.projects[pid]["summary"] = args[5]
                self.projects[pid]["last_scanned_at"] = datetime.now()
        elif "FINAL_SCORE" in q:
            new_score, pid = args[0], args[1]
            if pid in self.projects:
                self.projects[pid]["final_score"] = new_score
        elif "PROCESSED_DELIVERIES" in q:
            self.processed_deliveries.add(args[0])


    def transaction(self):
        class DummyTx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                pass

        return DummyTx()


@pytest.fixture
def mock_db():
    """Provides a stateful mock database instance for testing."""
    return StatefulMockDB()


@pytest.fixture(autouse=True)
def setup_mock_db_pool(mock_db):
    """Fixture to mock DB_POOL and override get_db_connection with stateful mock DB."""
    db_module.DB_POOL = mock_db

    async def override_get_db_connection():
        yield mock_db

    app.dependency_overrides[db_module.get_db_connection] = override_get_db_connection
    yield mock_db
    app.dependency_overrides.clear()
    db_module.DB_POOL = None



# ---------------------------------------------------------------------------
# 1. Complete End-to-End Master Lifecycle Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_master_e2e_lifecycle(mock_db):
    """Verify the complete TalentCaspian platform lifecycle across Steps 0-5.

    Lifecycle Flow:
    1. Register Student & Portfolio Project in Database
    2. Rater submits rating (9/10) -> recalculate Bayesian score
    3. Agent 1 GitHub scan + Gemini evaluation -> AI score & tags
    4. Recruiter creation with JSONB preference filters & matching
    5. Recruiter suggestion creation & GitHub push webhook auto-resolution
    6. Agent 2 Follow-Up Notification dispatch via Caspian SDK
    7. Admin notification batch process execution (POST /api/admin/notify)
    8. Audit log verification in notification_logs database table
    """
    # -----------------------------------------------------------------------
    # Step 1: Student & Project Creation
    # -----------------------------------------------------------------------
    student_record = await create_student(
        mock_db,
        {
            "name": "Alex E2E Dev",
            "email": "alex.e2e@talentcaspian.org",
            "github_username": "alex-e2e-dev",
        },
    )
    assert student_record["id"] is not None
    assert student_record["name"] == "Alex E2E Dev"

    project_record = await create_project(
        mock_db,
        {
            "student_id": student_record["id"],
            "repo_url": "https://github.com/alex-e2e-dev/smart-payment-gateway",
            "summary": "Initial submission for smart payment gateway project.",
            "tags": ["python"],
        },
    )
    assert project_record["id"] is not None
    assert project_record["repo_url"] == "https://github.com/alex-e2e-dev/smart-payment-gateway"

    # -----------------------------------------------------------------------
    # Step 2: Rating & Bayesian Score Calculation
    # -----------------------------------------------------------------------
    rating_entry = await add_project_rating(
        mock_db,
        {
            "project_id": project_record["id"],
            "rater_type": "public",
            "rater_id": None,
            "rater_ip_hash": "hash_ip_12345",
            "rating": 9,
        },
    )
    assert rating_entry["rating"] == 9

    updated_score_step2 = await update_project_score(mock_db, project_record["id"])
    # Bayesian calculation without AI score prior defaults AI score = 0, Bayesian rating = (25+9)/6 = 5.666...
    assert updated_score_step2 > 0.0

    # -----------------------------------------------------------------------
    # Step 3: Agent 1 GitHub Scan & Gemini Evaluation
    # -----------------------------------------------------------------------
    mock_scan_data = {
        "owner": "alex-e2e-dev",
        "repo": "smart-payment-gateway",
        "repo_url": "https://github.com/alex-e2e-dev/smart-payment-gateway",
        "stars": 42,
        "forks": 12,
        "language": "Python",
        "description": "Enterprise microservice gateway for payments",
        "default_branch": "main",
        "readme": "# Smart Payment Gateway\nFastAPI payment processing service.",
        "tree_structure": ["main.py", "auth.py", "tests/test_auth.py"],
        "source_files": {"main.py": "import fastapi\napp = fastapi.FastAPI()"},
    }

    mock_gemini_eval = {
        "ai_difficulty": 85.0,
        "ai_authenticity": 90.0,
        "ai_creativity": 80.0,
        "ai_score": calculate_weighted_ai_score(85.0, 90.0, 80.0),  # 85.0
        "tags": ["python", "fastapi", "postgresql"],
        "summary": "Enterprise-grade async FastAPI payment service with solid architecture.",
    }

    assert mock_gemini_eval["ai_score"] == 85.0

    await update_project_ai_scores(
        mock_db,
        project_id=project_record["id"],
        ai_difficulty=mock_gemini_eval["ai_difficulty"],
        ai_authenticity=mock_gemini_eval["ai_authenticity"],
        ai_creativity=mock_gemini_eval["ai_creativity"],
        ai_score=mock_gemini_eval["ai_score"],
        tags=mock_gemini_eval["tags"],
        summary=mock_gemini_eval["summary"],
    )

    project_after_ai = await get_project_by_id(mock_db, project_record["id"])
    assert project_after_ai["ai_score"] == 85.0
    assert "python" in project_after_ai["tags"]
    # Final score = 70% of AI score (85) + 30% of Bayesian rating (9 rating -> 56.666...)
    assert project_after_ai["final_score"] > 70.0

    # -----------------------------------------------------------------------
    # Step 4: Recruiter Creation & Matching Engine
    # -----------------------------------------------------------------------
    recruiter_record = await create_recruiter(
        mock_db,
        {
            "name": "Sarah Recruiter",
            "email": "sarah@techrecruiters.com",
            "preferred_channel": "email",
            "telegram_handle": "@sarah_tech",
            "preference_filters": {
                "tech_stack": ["python", "fastapi"],
                "min_score": 70.0,
            },
        },
    )
    assert recruiter_record["id"] is not None

    matched_recruiters = await find_matches(mock_db, project_record["id"])
    assert len(matched_recruiters) == 1
    assert matched_recruiters[0]["name"] == "Sarah Recruiter"

    matched_projects = await find_candidate_projects(mock_db, recruiter_record["id"])
    assert len(matched_projects) == 1
    assert matched_projects[0]["repo_url"] == project_record["repo_url"]

    # -----------------------------------------------------------------------
    # Step 5: Recruiter Suggestion & GitHub Push Webhook Auto-Resolution
    # -----------------------------------------------------------------------
    suggestion = await add_suggestion(
        mock_db,
        {
            "project_id": project_record["id"],
            "recruiter_id": recruiter_record["id"],
            "suggestion_text": "Add unit test suite for auth module",
        },
    )
    assert suggestion["resolved"] is False

    unresolved_before = await get_unresolved_suggestions(mock_db, project_record["id"])
    assert len(unresolved_before) == 1

    # Simulate GitHub push webhook event containing commit resolving suggestion
    webhook_payload = {
        "repository": {"html_url": project_record["repo_url"]},
        "commits": [
            {
                "message": "feat: add unit test suite for auth module",
                "added": ["tests/test_auth.py"],
                "modified": ["auth.py"],
            }
        ],
    }

    mock_caspian_client = MagicMock(spec=CommClient)
    mock_caspian_client.send_message.return_value = {"status": "sent", "id": "caspian_msg_1001"}

    from routers.webhook import process_push_webhook_bg

    with patch("routers.webhook.scan_github_repository", AsyncMock(return_value=mock_scan_data)), patch(
        "routers.webhook.evaluate_repository", AsyncMock(return_value=mock_gemini_eval)
    ), patch(
        "services.caspian_outreach.get_caspian_client", return_value=mock_caspian_client
    ):
        await process_push_webhook_bg(webhook_payload, "delivery-e2e-unique-001")

    # Verify suggestion marked resolved
    unresolved_after = await get_unresolved_suggestions(mock_db, project_record["id"])
    assert len(unresolved_after) == 0

    resolved_sugg = mock_db.suggestions[suggestion["id"]]
    assert resolved_sugg["resolved"] is True

    # Verify Agent 2 follow-up outreach was triggered by auto-resolution
    mock_caspian_client.send_message.assert_called()

    # -----------------------------------------------------------------------
    # Step 6: Agent 2 Caspian Outreach Dispatching
    # -----------------------------------------------------------------------
    outreach_msg = await generate_outreach_message(recruiter_record, project_after_ai)
    assert "Sarah" in outreach_msg

    assert "Alex E2E Dev" in outreach_msg
    assert "smart-payment-gateway" in outreach_msg

    dispatch_res = dispatch_message(recruiter_record, outreach_msg, client=mock_caspian_client)
    assert dispatch_res["status"] == "sent"

    # -----------------------------------------------------------------------
    # Step 7: Admin Notify Batch Execution (POST /api/admin/notify)
    # -----------------------------------------------------------------------
    with patch(
        "services.caspian_outreach.get_caspian_client", return_value=mock_caspian_client
    ), patch("routers.admin.process_notifications") as mock_admin_proc:
        resp = client.post(
            "/api/admin/notify",
            json={"project_id": project_record["id"], "recruiter_id": recruiter_record["id"]},
            headers={"X-Admin-API-Key": "dev_admin_key_12345"},
        )
        assert resp.status_code == 202
        resp_data = resp.json()
        assert resp_data["status"] == "queued"
        assert resp_data["project_id"] == project_record["id"]
        assert resp_data["recruiter_id"] == recruiter_record["id"]

    # -----------------------------------------------------------------------
    # Step 8: Notification Logs Audit Verification
    # -----------------------------------------------------------------------
    assert len(mock_db.notification_logs) > 0
    latest_log = mock_db.notification_logs[-1]
    assert latest_log["recruiter_id"] == recruiter_record["id"]
    assert latest_log["project_id"] == project_record["id"]
    assert latest_log["channel"] == "email"
    assert latest_log["is_followup"] is True


# ---------------------------------------------------------------------------
# 2. FastAPI HTTP API Integration Flow Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_master_e2e_api_flow(mock_db):
    """Verify HTTP API endpoints end-to-end via AsyncClient."""
    transport = ASGITransport(app=app)
    with (
        patch("routers.public.scan_github_repository") as mock_scan,
        patch("routers.public.evaluate_repository") as mock_eval,
        patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "skip_signature_verification"}),
    ):

        mock_scan.return_value = {
            "owner": "bobapidev",
            "repo": "api-e2e-repo",
            "language": "Python",
            "source_files": {"main.py": "print('hello')"},
        }
        mock_eval.return_value = {
            "ai_difficulty": 75.0,
            "ai_authenticity": 80.0,
            "ai_creativity": 70.0,
            "ai_score": 75.0,
            "tags": ["python", "fastapi"],
            "summary": "FastAPI backend service",
        }
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:

            # 1. POST /api/register
            reg_resp = await ac.post(
                "/api/register",
                json={
                    "name": "Bob API Dev",
                    "email": "bob@apidev.org",
                    "github_username": "bobapidev",
                    "repo_url": "https://github.com/bobapidev/api-e2e-repo",
                },
            )
            assert reg_resp.status_code == 201
            reg_data = reg_resp.json()
            assert reg_data["status"] == "success"
            project_id = reg_data["project"]["id"]

            # Set scores manually in mock DB to simulate scanner completion
            await update_project_ai_scores(
                mock_db,
                project_id=project_id,
                ai_difficulty=75.0,
                ai_authenticity=80.0,
                ai_creativity=70.0,
                ai_score=75.0,
                tags=["python", "fastapi"],
                summary="FastAPI backend service",
            )

            # 2. POST /api/rate
            rate_resp = await ac.post(
                "/api/rate",
                json={
                    "project_id": project_id,
                    "rater_type": "public",
                    "rating": 10,
                },
            )
            assert rate_resp.status_code == 201
            assert rate_resp.json()["new_final_score"] > 0.0

            # 3. GET /api/dashboard
            dash_resp = await ac.get("/api/dashboard?page=1&limit=10")
            assert dash_resp.status_code == 200
            dash_data = dash_resp.json()
            assert dash_data["total"] >= 1
            assert any(p["id"] == project_id for p in dash_data["items"])

            # 4. POST /api/webhook/github (Webhook ingestion endpoint)
            webhook_body = json.dumps(
                {
                    "repository": {"html_url": "https://github.com/bobapidev/api-e2e-repo"},
                    "commits": [{"message": "feat: add missing feature", "modified": ["main.py"]}],
                }
            ).encode("utf-8")

            webhook_resp = await ac.post(
                "/api/webhook/github",
                content=webhook_body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Delivery": "delivery-api-e2e-1234",
                    "X-GitHub-Event": "push",
                },
            )
            assert webhook_resp.status_code == 202
            assert webhook_resp.json()["status"] == "accepted"

            # 5. POST /api/admin/notify (Admin notify endpoint)
            admin_resp = await ac.post(
                "/api/admin/notify",
                json={"project_id": project_id},
                headers={"X-Admin-API-Key": "dev_admin_key_12345"},
            )
            assert admin_resp.status_code == 202
            assert admin_resp.json()["status"] == "queued"


# ---------------------------------------------------------------------------
# 3. Multi-Channel & Cooldown Integration Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_multi_recruiter_channels_and_cooldown(mock_db):
    """Verify multi-channel dispatching (Email vs Telegram) and 7-day cooldown rules."""
    mock_caspian = MagicMock(spec=CommClient)
    mock_caspian.send_message.return_value = {"status": "sent", "id": "msg_99"}

    # Recruiter 1: Email channel
    r1 = await create_recruiter(
        mock_db,
        {
            "name": "Email Recruiter",
            "email": "r1@corp.com",
            "preferred_channel": "email",
            "preference_filters": {"tech_stack": ["python"]},
        },
    )

    # Recruiter 2: Telegram channel
    r2 = await create_recruiter(
        mock_db,
        {
            "name": "Telegram Recruiter",
            "email": "r2@corp.com",
            "preferred_channel": "telegram",
            "telegram_handle": "@tg_recruiter",
            "preference_filters": {"tech_stack": ["python"]},
        },
    )

    student = await create_student(
        mock_db, {"name": "Multi Dev", "email": "multi@dev.org", "github_username": "multidev"}
    )
    proj = await create_project(
        mock_db, {"student_id": student["id"], "repo_url": "https://github.com/multidev/app"}
    )
    await update_project_ai_scores(
        mock_db, proj["id"], 80.0, 80.0, 80.0, 80.0, ["python"], "Python App"
    )

    # Process notification batch
    res_batch = await process_notifications(
        project_id=proj["id"], pool=mock_db, client=mock_caspian
    )
    assert res_batch["processed_count"] == 2
    assert mock_caspian.send_message.call_count == 2

    # Second call should skip due to 7-day cooldown
    res_cooldown = await process_notifications(
        project_id=proj["id"], pool=mock_db, client=mock_caspian
    )
    assert res_cooldown["processed_count"] == 0
    assert res_cooldown["skipped_count"] == 2

    # Follow-up notification bypasses cooldown
    res_followup = await send_followup_notification(
        recruiter_id=r1["id"],
        project_id=proj["id"],
        suggestion_text="Add documentation",
        pool=mock_db,
        client=mock_caspian,
    )
    assert res_followup["status"] == "completed"
    assert res_followup["is_followup"] is True


# ---------------------------------------------------------------------------
# 4. Resilience and Boundary Conditions Integration Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_boundary_and_resilience(mock_db):
    """Verify security controls, delivery idempotency, and error recovery."""
    transport = ASGITransport(app=app)
    with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "skip_signature_verification"}):
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:

            # 1. Webhook with invalid HMAC signature
            with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "secret_key"}):
                bad_sig_resp = await ac.post(
                    "/api/webhook/github",
                    json={"repository": {"html_url": "https://github.com/test/repo"}},
                    headers={
                        "Content-Type": "application/json",
                        "X-GitHub-Delivery": "del-invalid-sig",
                        "X-GitHub-Event": "push",
                        "X-Hub-Signature-256": "sha256=invalid_hash_signature",
                    },
                )
                assert bad_sig_resp.status_code == 401

            # 2. Webhook idempotency duplicate delivery check
            mock_db.processed_deliveries.add("del-dup-001")
            dup_resp = await ac.post(
                "/api/webhook/github",
                json={"repository": {"html_url": "https://github.com/test/repo"}},
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Delivery": "del-dup-001",
                    "X-GitHub-Event": "push",
                },
            )
            assert dup_resp.status_code == 202
            assert dup_resp.json()["reason"] == "duplicate delivery"



            # 3. Non-push webhook event (e.g. ping / issues) ignored cleanly
            ping_resp = await ac.post(
                "/api/webhook/github",
                json={"zen": "Non-blocking is better than blocking."},
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Delivery": "del-ping-001",
                    "X-GitHub-Event": "ping",
                },
            )
            assert ping_resp.status_code == 202
            assert ping_resp.json()["status"] == "ignored"

            # 4. Unauthorized admin endpoint access
            unauth_admin = await ac.post("/api/admin/notify", json={"project_id": 1})
            assert unauth_admin.status_code == 401

            bad_admin_key = await ac.post(
                "/api/admin/notify",
                json={"project_id": 1},
                headers={"X-Admin-API-Key": "wrong_api_key"},
            )
            assert bad_admin_key.status_code == 401


# ---------------------------------------------------------------------------
# 5. Master Closed-Loop E2E Test: Step 5 Outreach -> Step 6 Reply -> Step 4 Resolution -> Step 5 Follow-Up
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_closed_loop_recruiter_reply_to_followup(mock_db):
    """Verify full end-to-end multi-agent feedback loop across all steps:
    1. Student & Project Registration
    2. Recruiter Registration & Match Discovery
    3. Agent 2 initial Caspian Outreach Dispatching & notification_logs recording
    4. Recruiter sends reply message processed by Step 6 Listener Agent (caspian_agent)
    5. Step 6 Listener resolves recruiter identity and project context via notification_logs,
       creates an unresolved suggestion and adds a recruiter rating, updating project final_score.
    6. Student pushes GitHub commit resolving the suggestion.
    7. GitHub Webhook triggers Agent 1 Scanner auto-resolution of suggestion.
    8. Agent 1 auto-resolution triggers Agent 2 follow-up notification dispatch to recruiter.
    """
    mock_caspian = MagicMock(spec=CommClient)
    mock_caspian.send_message.return_value = {"status": "sent", "id": "caspian_closed_loop_001"}

    # Step 1: Create Student & Project
    student = await create_student(
        mock_db,
        {"name": "Carol ClosedLoop", "email": "carol@closedloop.org", "github_username": "carolloop"},
    )
    project = await create_project(
        mock_db,
        {"student_id": student["id"], "repo_url": "https://github.com/carolloop/ai-agent"},
    )
    await update_project_ai_scores(
        mock_db, project["id"], 85.0, 90.0, 80.0, 85.0, ["python", "ai"], "AI Agent Framework"
    )

    # Step 2: Create Recruiter
    recruiter = await create_recruiter(
        mock_db,
        {
            "name": "David Recruiter",
            "email": "david@techhire.com",
            "preferred_channel": "email",
            "preference_filters": {"tech_stack": ["python"], "min_score": 70.0},
        },
    )

    # Step 3: Agent 2 Outreach Notification Batch Process
    batch_res = await process_notifications(
        project_id=project["id"], pool=mock_db, client=mock_caspian
    )
    assert batch_res["processed_count"] == 1
    assert len(mock_db.notification_logs) == 1
    log = mock_db.notification_logs[0]
    assert log["recruiter_id"] == recruiter["id"]
    assert log["project_id"] == project["id"]

    # Step 4 & 5: Recruiter replies via Caspian Channel (Step 6 Listener Agent)
    mock_reply_msg = MagicMock(spec=Message)
    mock_reply_msg.channel = "email"
    mock_reply_msg.sender = "david@techhire.com"
    mock_reply_msg.text = "Great AI project! Rating: 9/10. Suggestion: add Dockerfile and docker-compose"
    mock_reply_msg.reply = MagicMock()

    from caspian_agent import process_inbound_message

    with patch.object(db_module, "DB_POOL", mock_db), patch.object(db_module, "is_pool_ready", return_value=True):
        listener_res = await process_inbound_message(mock_reply_msg)

    assert listener_res["status"] == "processed"
    assert listener_res["recruiter_id"] == recruiter["id"]
    assert listener_res["project_id"] == project["id"]
    assert listener_res["suggestion_added"] is True
    assert listener_res["rating_added"] is True

    # Verify suggestion stored with resolved=False
    unresolved_suggs = await get_unresolved_suggestions(mock_db, project["id"])
    assert len(unresolved_suggs) == 1
    assert "Dockerfile" in unresolved_suggs[0]["suggestion_text"]
    assert unresolved_suggs[0]["resolved"] is False

    # Verify rating recorded and score updated
    updated_proj = await get_project_by_id(mock_db, project["id"])
    assert updated_proj["final_score"] is not None

    # Step 6 & 7: Student pushes commit resolving the suggestion (GitHub Webhook -> Agent 1)
    webhook_payload = {
        "repository": {"html_url": project["repo_url"]},
        "commits": [
            {
                "message": "feat: add Dockerfile and docker-compose setup",
                "added": ["Dockerfile", "docker-compose.yml"],
            }
        ],
    }

    mock_scan_data = {
        "owner": "carolloop",
        "repo": "ai-agent",
        "language": "Python",
        "source_files": {"Dockerfile": "FROM python:3.11", "main.py": "print('ai')"},
    }
    mock_gemini_eval = {
        "ai_difficulty": 85.0,
        "ai_authenticity": 92.0,
        "ai_creativity": 85.0,
        "ai_score": 87.0,
        "tags": ["python", "ai", "docker"],
        "summary": "AI Agent with Docker containerization",
    }

    from routers.webhook import process_push_webhook_bg

    with patch("routers.webhook.scan_github_repository", AsyncMock(return_value=mock_scan_data)), patch(
        "routers.webhook.evaluate_repository", AsyncMock(return_value=mock_gemini_eval)
    ), patch(
        "services.caspian_outreach.get_caspian_client", return_value=mock_caspian
    ):
        await process_push_webhook_bg(webhook_payload, "delivery-closed-loop-e2e")

    # Step 8: Verify suggestion marked resolved and Agent 2 follow-up outreach sent
    unresolved_after = await get_unresolved_suggestions(mock_db, project["id"])
    assert len(unresolved_after) == 0

    # Verify follow-up log recorded in notification_logs
    followup_logs = [l for l in mock_db.notification_logs if l.get("is_followup")]
    assert len(followup_logs) == 1
    assert followup_logs[0]["recruiter_id"] == recruiter["id"]
    assert followup_logs[0]["project_id"] == project["id"]

