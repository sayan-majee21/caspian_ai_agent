"""Notification Orchestrator Service for TalentCaspian Agent 2.

Coordinates matching, deduplication checking (7-day cooldown), message generation,
Caspian dispatching, and logging for standard outreach and follow-up flows.
"""

import asyncio
import logging
from typing import Any

import asyncpg

import database.db as db
from services.caspian_outreach import dispatch_message
from services.matching_engine import find_matches
from services.outreach_service import generate_followup_message, generate_outreach_message

logger = logging.getLogger("talentcaspian.notification_service")


async def process_notifications(
    project_id: int,
    recruiter_id: int | None = None,
    pool: asyncpg.Pool | asyncpg.Connection | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Execute matching, deduplication checking, generation, dispatch, and logging for a project.

    Args:
        project_id (int): Target project ID.
        recruiter_id (int | None): Optional single recruiter ID. If None, matches all candidate recruiters.
        pool (asyncpg.Pool | asyncpg.Connection | None): Database pool or connection override.
        client (Any | None): Optional Caspian CommClient override.

    Returns:
        dict[str, Any]: Processing status summary.
    """
    try:
        db_conn = pool or db.DB_POOL
        if db_conn is None:
            logger.error("Database connection pool is not initialized in process_notifications.")
            return {"status": "error", "message": "Database connection pool unavailable"}

        project = await db.get_project_by_id(db_conn, project_id)
        if not project:
            logger.warning(f"Project id={project_id} not found for notification processing.")
            return {"status": "error", "message": f"Project {project_id} not found"}

        if recruiter_id is not None:
            recruiter = await db.get_recruiter_by_id(db_conn, recruiter_id)
            if not recruiter:
                logger.warning(f"Recruiter id={recruiter_id} not found.")
                return {"status": "error", "message": f"Recruiter {recruiter_id} not found"}
            recruiters = [recruiter]
        else:
            recruiters = await find_matches(db_conn, project_id)

        processed_count = 0
        skipped_count = 0

        for rec in recruiters:
            rec_id = rec["id"]
            try:
                # Deduplication check (7-day cooldown for standard notifications)
                recent = await db.has_recent_notification(
                    db_conn, recruiter_id=rec_id, project_id=project_id, within_days=7
                )
                if recent:
                    logger.info(
                        f"Skipping notification for recruiter_id={rec_id}, project_id={project_id} "
                        f"due to recent notification within 7-day cooldown."
                    )
                    skipped_count += 1
                    continue

                message = await generate_outreach_message(rec, project)
                dispatch_res = await asyncio.to_thread(dispatch_message, rec, message, client=client)

                channel = rec.get("preferred_channel", "email") or "email"
                await db.create_notification_log(
                    db_conn,
                    recruiter_id=rec_id,
                    project_id=project_id,
                    channel=channel,
                    is_followup=False,
                )
                processed_count += 1
                logger.info(
                    f"Successfully processed notification for recruiter_id={rec_id}, project_id={project_id}"
                )
            except Exception as rec_exc:
                logger.error(
                    f"Failed processing notification for recruiter_id={rec_id}, project_id={project_id}: {rec_exc}",
                    exc_info=True,
                )

        return {
            "status": "completed",
            "project_id": project_id,
            "processed_count": processed_count,
            "skipped_count": skipped_count,
        }
    except Exception as exc:
        logger.error(f"Error executing process_notifications background task: {exc}")
        return {"status": "error", "message": str(exc)}


async def send_followup_notification(
    recruiter_id: int,
    project_id: int,
    suggestion_text: str,
    pool: asyncpg.Pool | asyncpg.Connection | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Execute follow-up notification flow when a recruiter's suggestion is resolved by a student.

    Bypasses the 7-day cooldown check and logs the notification with is_followup=True.

    Args:
        recruiter_id (int): Recruiter ID who submitted the original suggestion.
        project_id (int): Project ID that was updated.
        suggestion_text (str): Recruiter's original suggestion text.
        pool (asyncpg.Pool | asyncpg.Connection | None): Database pool or connection override.
        client (Any | None): Optional Caspian CommClient override.

    Returns:
        dict[str, Any]: Follow-up dispatch status.
    """
    db_conn = pool or db.DB_POOL
    if db_conn is None:
        logger.error("Database connection pool unavailable for send_followup_notification.")
        return {"status": "error", "message": "Database connection pool unavailable"}

    recruiter = await db.get_recruiter_by_id(db_conn, recruiter_id)
    if not recruiter:
        logger.warning(f"Recruiter id={recruiter_id} not found for follow-up.")
        return {"status": "error", "message": f"Recruiter {recruiter_id} not found"}

    project = await db.get_project_by_id(db_conn, project_id)
    if not project:
        logger.warning(f"Project id={project_id} not found for follow-up.")
        return {"status": "error", "message": f"Project {project_id} not found"}

    message = generate_followup_message(recruiter, project, suggestion_text)
    dispatch_res = await asyncio.to_thread(dispatch_message, recruiter, message, client=client)


    channel = recruiter.get("preferred_channel", "email") or "email"
    await db.create_notification_log(
        db_conn,
        recruiter_id=recruiter_id,
        project_id=project_id,
        channel=channel,
        is_followup=True,
    )

    logger.info(
        f"Follow-up notification sent to recruiter_id={recruiter_id} for project_id={project_id}"
    )
    return {
        "status": "completed",
        "is_followup": True,
        "recruiter_id": recruiter_id,
        "project_id": project_id,
        "dispatch_result": dispatch_res,
    }
