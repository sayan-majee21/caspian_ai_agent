"""Admin and background process API stub endpoints for TalentCaspian."""

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger("talentcaspian.admin")

router = APIRouter(prefix="/api/admin", tags=["Admin & Background Stubs"])


class AdminScanRequest(BaseModel):
    """Payload schema for triggering AI scanning process."""

    project_id: Optional[int] = Field(
        None, description="Optional project ID to scan. If None, scans all pending projects."
    )


class AdminNotifyRequest(BaseModel):
    """Payload schema for triggering recruiter notification process."""

    project_id: int = Field(..., description="Project ID to send notifications for.")
    recruiter_id: Optional[int] = Field(
        None, description="Optional single recruiter ID to notify. If None, scans all matching recruiters."
    )


def verify_admin_key(x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key")) -> None:
    """Dependency to verify the admin API key.

    Args:
        x_admin_api_key (Optional[str]): Provided X-Admin-API-Key header value.

    Raises:
        HTTPException: If key is missing or invalid.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "dev_admin_key_12345")
    if expected_key and x_admin_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-API-Key header",
        )


@router.post(
    "/scan",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger AI project scan stub",
    description="Triggers the background AI code scanning process (Agent 1 stub).",
)
async def trigger_admin_scan(
    payload: AdminScanRequest,
    x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key"),
) -> dict[str, Any]:
    """Trigger AI scanning process stub.

    Args:
        payload (AdminScanRequest): Scan parameters.
        x_admin_api_key (Optional[str]): Admin API Key header.

    Returns:
        dict[str, Any]: Queued status and metadata.
    """
    verify_admin_key(x_admin_api_key)
    logger.info(f"Admin scan triggered for project_id={payload.project_id}")

    return {
        "status": "queued",
        "message": "AI scanning process queued",
        "project_id": payload.project_id,
    }


@router.post(
    "/notify",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger recruiter notification scan stub",
    description="Triggers the background Caspian multi-channel recruiter notification process (Agent 2 stub).",
)
async def trigger_admin_notify(
    payload: AdminNotifyRequest,
    x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key"),
) -> dict[str, Any]:
    """Trigger recruiter notification stub.

    Args:
        payload (AdminNotifyRequest): Notification parameters.
        x_admin_api_key (Optional[str]): Admin API Key header.

    Returns:
        dict[str, Any]: Queued status and metadata.
    """
    verify_admin_key(x_admin_api_key)
    logger.info(
        f"Admin notify triggered for project_id={payload.project_id}, recruiter_id={payload.recruiter_id}"
    )

    return {
        "status": "queued",
        "message": "Notification process queued",
        "project_id": payload.project_id,
        "recruiter_id": payload.recruiter_id,
    }
