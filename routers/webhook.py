"""GitHub Webhook API Router for TalentCaspian Agent 1.

Processes GitHub push webhooks asynchronously with HMAC SHA256 signature verification,
delivery idempotency enforcement, push update classification, and automated project re-evaluation.
"""

import hashlib
import hmac
import logging
import os
from typing import Any
import asyncpg
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

import database.db as db_module
from database.db import (
    add_commit_log,
    get_project_by_repo_url,
    get_unresolved_suggestions,
    is_delivery_processed,
    mark_suggestion_resolved,
    record_delivery_processed,
    update_project_ai_scores,
)
from services.gemini_scanner import (
    check_suggestion_resolution,
    classify_push_update,
    evaluate_repository,
)
from services.github_service import scan_github_repository
from services.notification_service import send_followup_notification


logger = logging.getLogger("talentcaspian.webhook")

router = APIRouter(prefix="/api/webhook", tags=["Webhooks"])

# In-memory delivery cache for single-worker instant checks
_in_memory_delivery_cache: set[str] = set()


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Verify HMAC SHA256 signature of GitHub webhook payload.

    Args:
        secret (str): Webhook secret key.
        body (bytes): Raw request body bytes.
        signature_header (str | None): Value of X-Hub-Signature-256 header.

    Returns:
        bool: True if signature matches, False otherwise.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    received_sig = signature_header.split("sha256=")[1].strip()
    computed_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_sig, received_sig)


async def process_push_webhook_bg(payload: dict[str, Any], delivery_id: str) -> None:
    """Background task handler for processing GitHub push webhooks.

    Executes outside HTTP lifecycle, acquiring database connection pool directly.

    Args:
        payload (dict[str, Any]): GitHub webhook JSON payload.
        delivery_id (str): Unique delivery UUID.
    """
    if not db_module.is_pool_ready() or db_module.DB_POOL is None:
        logger.error("DB Pool not ready in background webhook processing.")
        return

    project = None
    async with db_module.DB_POOL.acquire() as conn:
        # Record delivery idempotency in database
        await record_delivery_processed(conn, delivery_id)
        _in_memory_delivery_cache.add(delivery_id)

        # Extract repo URL
        repo_data = payload.get("repository", {})
        repo_url = (
            repo_data.get("html_url")
            or repo_data.get("clone_url")
            or repo_data.get("url")
            or ""
        )
        if not repo_url and repo_data.get("full_name"):
            repo_url = f"https://github.com/{repo_data['full_name']}"

        if not repo_url:
            logger.warning("No repository URL found in webhook payload.")
            return

        project = await get_project_by_repo_url(conn, repo_url)
        if not project:
            logger.info(f"No registered project found for repository URL: {repo_url}")
            return

    # Extract commits and modified file paths
    commits = payload.get("commits", [])
    commit_messages = [c.get("message", "") for c in commits if c.get("message")]
    modified_files: list[str] = []
    for c in commits:
        modified_files.extend(c.get("added", []))
        modified_files.extend(c.get("modified", []))
        modified_files.extend(c.get("removed", []))
    modified_files = list(set(modified_files))

    # Classify update: Major vs. Minor
    classification = await classify_push_update(commit_messages, modified_files)
    logger.info(f"Push classification for project {project['id']}: {classification}")

    # Persist commit logs to commit_logs table
    if commits and db_module.is_pool_ready() and db_module.DB_POOL is not None:
        try:
            async with db_module.DB_POOL.acquire() as log_conn:
                for c in commits:
                    msg = c.get("message", "")
                    if msg:
                        author = c.get("author", {}).get("name") or c.get("author", {}).get("username") or "Developer"
                        await add_commit_log(
                            log_conn,
                            {
                                "project_id": project["id"],
                                "commit_hash": (c.get("id") or c.get("sha") or "")[:12],
                                "commit_message": msg,
                                "author_name": author,
                                "classification": classification,
                            },
                        )
        except Exception as log_exc:
            logger.warning(f"Failed to record commit log for project {project['id']}: {log_exc}")

    if classification == "Minor":
        logger.info(f"Minor push for project {project['id']} ignored.")
        return

    # Major update flow: full scan & evaluation (network I/O without holding DB connection)
    logger.info(f"Triggering full scan & re-evaluation for project {project['id']}.")
    try:
        repo_context = await scan_github_repository(project["repo_url"])
        eval_res = await evaluate_repository(repo_context)

        # Re-acquire DB connection for updates and follow-ups
        async with db_module.DB_POOL.acquire() as conn:
            await update_project_ai_scores(
                conn,
                project_id=project["id"],
                ai_difficulty=eval_res["ai_difficulty"],
                ai_authenticity=eval_res["ai_authenticity"],
                ai_creativity=eval_res["ai_creativity"],
                ai_score=eval_res["ai_score"],
                tags=eval_res["tags"],
                summary=eval_res["summary"],
            )
            logger.info(f"Successfully re-evaluated project {project['id']} on major push.")

            # Check for unresolved recruiter suggestions
            unresolved = await get_unresolved_suggestions(conn, project["id"])
            for sugg in unresolved:
                is_resolved = await check_suggestion_resolution(
                    sugg["suggestion_text"], commit_messages, modified_files
                )
                if is_resolved:
                    await mark_suggestion_resolved(conn, sugg["id"])
                    logger.info(
                        f"Recruiter suggestion #{sugg['id']} for project {project['id']} marked as resolved."
                    )
                    await send_followup_notification(
                        recruiter_id=sugg["recruiter_id"],
                        project_id=project["id"],
                        suggestion_text=sugg["suggestion_text"],
                        pool=conn,
                    )

    except Exception as exc:
        logger.error(f"Error processing major push evaluation for project {project['id']}: {exc}")



@router.post(
    "/github",
    status_code=status.HTTP_202_ACCEPTED,
    summary="GitHub push webhook handler",
    description="Validates HMAC signature, checks delivery idempotency, and enqueues push event processing.",
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_github_delivery: str | None = Header(None, alias="X-GitHub-Delivery"),
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
) -> dict[str, Any]:
    """Validate and process incoming GitHub webhook requests.

    Args:
        request (Request): FastAPI Request object.
        background_tasks (BackgroundTasks): FastAPI BackgroundTasks manager.
        x_hub_signature_256 (str | None): HMAC SHA256 signature header.
        x_github_delivery (str | None): Unique delivery UUID header.
        x_github_event (str | None): GitHub event header.

    Returns:
        dict[str, Any]: Status summary response.
    """
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "default_secret")
    body_bytes = await request.body()

    # 1. HMAC Verification
    if secret != "skip_signature_verification":
        if not verify_signature(secret, body_bytes, x_hub_signature_256):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid X-Hub-Signature-256 HMAC signature",
            )

    delivery_id = x_github_delivery or hashlib.md5(body_bytes).hexdigest()

    # 2. Delivery Idempotency Check
    if delivery_id in _in_memory_delivery_cache:
        return {"status": "ignored", "reason": "duplicate delivery", "delivery_id": delivery_id}

    if db_module.is_pool_ready() and db_module.DB_POOL is not None:
        try:
            async with db_module.DB_POOL.acquire() as db_conn:
                if await is_delivery_processed(db_conn, delivery_id):
                    _in_memory_delivery_cache.add(delivery_id)
                    return {
                        "status": "ignored",
                        "reason": "duplicate delivery",
                        "delivery_id": delivery_id,
                    }
        except Exception as exc:
            logger.warning(f"Failed idempotency DB check: {exc}")

    # 3. Event Filtering
    event_type = x_github_event or "push"
    if event_type.lower() != "push":
        return {
            "status": "ignored",
            "reason": f"unhandled event type '{event_type}'",
            "delivery_id": delivery_id,
        }

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload in request body",
        )

    # 4. Enqueue Background Processing and Return 202 Accepted
    background_tasks.add_task(process_push_webhook_bg, payload, delivery_id)

    return {
        "status": "accepted",
        "delivery_id": delivery_id,
        "message": "Webhook push event received and queued for evaluation.",
    }
