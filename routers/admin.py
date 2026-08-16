"""Admin and background process API stub endpoints for TalentCaspian."""

import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from pydantic import BaseModel, Field

import database.db as db_module
from services.notification_service import process_notifications


logger = logging.getLogger("talentcaspian.admin")


router = APIRouter(prefix="/api/admin", tags=["Admin & Background Stubs"])


class AdminScanRequest(BaseModel):
    """Payload schema for triggering AI scanning process."""

    project_id: int | None = Field(
        None, description="Optional project ID to scan. If None, scans all pending projects."
    )


class AdminNotifyRequest(BaseModel):
    """Payload schema for triggering recruiter notification process."""

    project_id: int = Field(..., description="Project ID to send notifications for.")
    recruiter_id: int | None = Field(
        None, description="Optional single recruiter ID to notify. If None, scans all matching recruiters."
    )


def verify_admin_key(x_admin_api_key: str | None = Header(None, alias="X-Admin-API-Key")) -> None:
    """Dependency to verify the admin API key using constant-time comparison.

    Args:
        x_admin_api_key (str | None): Provided X-Admin-API-Key header value.

    Raises:
        HTTPException: If key is missing or invalid.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "dev_admin_key_12345")
    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-API-Key header",
        )


@router.post(
    "/scan",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger AI project scan process",
    description="Triggers the background AI code scanning process (Agent 1).",
)
async def trigger_admin_scan(
    payload: AdminScanRequest,
    background_tasks: BackgroundTasks,
    x_admin_api_key: str | None = Header(None, alias="X-Admin-API-Key"),
) -> dict[str, Any]:
    """Trigger AI scanning background process.

    Args:
        payload (AdminScanRequest): Scan parameters.
        background_tasks (BackgroundTasks): FastAPI background task manager.
        x_admin_api_key (str | None): Admin API Key header.

    Returns:
        dict[str, Any]: Queued status and metadata.
    """
    verify_admin_key(x_admin_api_key)
    logger.info(f"Admin scan triggered for project_id={payload.project_id}")

    if payload.project_id and db_module.is_pool_ready() and db_module.DB_POOL is not None:
        try:
            from database.db import get_project_by_id
            from routers.public import scan_and_evaluate_project_bg
            async with db_module.DB_POOL.acquire() as conn:
                project = await get_project_by_id(conn, payload.project_id)
                if project and project.get("repo_url"):
                    background_tasks.add_task(
                        scan_and_evaluate_project_bg, payload.project_id, project["repo_url"]
                    )
        except Exception as exc:
            logger.warning(f"Failed to lookup project for admin scan: {exc}")


    return {
        "status": "queued",
        "message": "AI scanning process queued",
        "project_id": payload.project_id,
    }



@router.post(
    "/notify",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger recruiter notification scan",
    description="Triggers the background Caspian multi-channel recruiter notification process (Agent 2).",
)
async def trigger_admin_notify(
    payload: AdminNotifyRequest,
    background_tasks: BackgroundTasks,
    x_admin_api_key: str | None = Header(None, alias="X-Admin-API-Key"),
) -> dict[str, Any]:
    """Trigger recruiter notification background process.

    Args:
        payload (AdminNotifyRequest): Notification parameters.
        background_tasks (BackgroundTasks): FastAPI background task manager.
        x_admin_api_key (str | None): Admin API Key header.

    Returns:
        dict[str, Any]: Queued status and metadata.
    """
    verify_admin_key(x_admin_api_key)
    logger.info(
        f"Admin notify triggered for project_id={payload.project_id}, recruiter_id={payload.recruiter_id}"
    )

    background_tasks.add_task(
        process_notifications, project_id=payload.project_id, recruiter_id=payload.recruiter_id
    )

    return {
        "status": "queued",
        "message": "Notification process queued",
        "project_id": payload.project_id,
        "recruiter_id": payload.recruiter_id,
    }


