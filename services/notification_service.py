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

                if dispatch_res.get("status") != "failed":
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
                else:
                    logger.warning(
                        f"Notification dispatch returned failed for recruiter_id={rec_id}, project_id={project_id}: {dispatch_res.get('error')}"
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


async def notify_student_of_suggestion(
    project_id: int,
    recruiter_id: int,
    suggestion_text: str,
    pool: asyncpg.Pool | asyncpg.Connection | None = None,
    client: Any | None = None,
    project: dict[str, Any] | None = None,
    recruiter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute student notification when a recruiter submits constructive feedback or a suggestion.

    Args:
        project_id (int): Project ID that received the suggestion.
        recruiter_id (int): Recruiter ID who left the suggestion.
        suggestion_text (str): Suggestion feedback content.
        pool (asyncpg.Pool | asyncpg.Connection | None): Optional database pool or connection.
        client (Any | None): Optional Caspian CommClient override.
        project (dict[str, Any] | None): Optional pre-fetched project record.
        recruiter (dict[str, Any] | None): Optional pre-fetched recruiter record.

    Returns:
        dict[str, Any]: Notification dispatch status summary.
    """
    db_conn = pool or db.DB_POOL

    proj = project
    rec = recruiter
    student = None

    try:
        if db_conn is not None:
            if proj is None:
                proj = await db.get_project_by_id(db_conn, project_id)
            if rec is None:
                rec = await db.get_recruiter_by_id(db_conn, recruiter_id)
            if proj:
                student_id = proj.get("student_id")
                if student_id:
                    student = await db.get_student_by_id(db_conn, student_id)
                elif proj.get("student_email"):
                    student = {
                        "id": proj.get("student_id", 0),
                        "name": proj.get("student_name", "Developer"),
                        "email": proj.get("student_email"),
                    }
    except Exception as fetch_err:
        logger.warning(f"Error fetching metadata for student notification: {fetch_err}")

    if not proj:
        logger.warning(f"Project id={project_id} not found for student notification.")
        return {"status": "error", "message": f"Project {project_id} not found"}

    if not student or not student.get("email"):
        logger.warning(f"Student not found or missing email for project_id={project_id}")
        return {"status": "error", "message": "Student not found or missing email"}

    recruiter_name = rec.get("name", "A Tech Recruiter") if rec else "A Tech Recruiter"
    repo_url = proj.get("repo_url") or ""
    repo_name = repo_url.rstrip("/").split("/")[-1] if repo_url else f"Project #{project_id}"

    message = (
        f"Hi {student.get('name', 'Developer')},\n\n"
        f"Great news! {recruiter_name} from our verified recruiter network just reviewed your project '{repo_name}' and left the following suggestion for improvement:\n\n"
        f"💬 \"{suggestion_text}\"\n\n"
        f"💡 Tip: When you address this feedback and push updates to your GitHub repository, TalentCaspian will automatically analyze your changes, update your score, and notify the recruiter!\n\n"
        f"Check your Personal Analytics dashboard to view detailed feedback."
    )

    student_recipient = {
        "id": student["id"],
        "email": student["email"],
        "preferred_channel": "email",
    }

    try:
        dispatch_res = await asyncio.to_thread(dispatch_message, student_recipient, message, client=client)
    except Exception as send_err:
        logger.warning(f"Failed to dispatch student notification email: {send_err}")
        dispatch_res = {"status": "failed", "error": str(send_err)}

    logger.info(
        f"Dispatched recruiter suggestion notification to student {student['email']} for project #{project_id}"
    )
    return {
        "status": "completed",
        "student_id": student["id"],
        "student_email": student["email"],
        "project_id": project_id,
        "dispatch_result": dispatch_res,
    }
