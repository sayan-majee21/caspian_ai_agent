"""Public and Student API endpoints for TalentCaspian."""

import hashlib
import logging
from typing import Any

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field

import database.db as db_module
from database.db import (
    add_project_rating,
    create_project,
    create_student,
    get_db_connection,
    get_projects_feed,
    update_project_ai_scores,
    update_project_score,
)
from services.gemini_scanner import evaluate_repository
from services.github_service import scan_github_repository

logger = logging.getLogger("talentcaspian.public")

router = APIRouter(prefix="/api", tags=["Public & Students"])


async def scan_and_evaluate_project_bg(project_id: int, repo_url: str) -> None:
    """Background task to scan and evaluate a student's portfolio project upon registration.

    Args:
        project_id (int): Project ID.
        repo_url (str): GitHub repository URL.
    """
    if not db_module.is_pool_ready() or db_module.DB_POOL is None:
        return
    try:
        repo_context = await scan_github_repository(repo_url)
        eval_res = await evaluate_repository(repo_context)
        async with db_module.DB_POOL.acquire() as conn:
            await update_project_ai_scores(
                conn,
                project_id=project_id,
                ai_difficulty=eval_res["ai_difficulty"],
                ai_authenticity=eval_res["ai_authenticity"],
                ai_creativity=eval_res["ai_creativity"],
                ai_score=eval_res["ai_score"],
                tags=eval_res["tags"],
                summary=eval_res["summary"],
            )
            logger.info(f"Initial scan and evaluation completed for project #{project_id}")
    except Exception as exc:
        logger.error(f"Error during initial scanning of project #{project_id}: {exc}")


class StudentRegisterRequest(BaseModel):
    """Payload schema for student registration."""

    name: str = Field(..., min_length=1, description="Student full name")
    email: EmailStr = Field(..., description="Student email address")
    github_username: str = Field(..., min_length=1, description="GitHub username")
    repo_url: str | None = Field(None, description="Optional initial GitHub project repository URL")


class ProjectRatingRequest(BaseModel):
    """Payload schema for project rating submission."""

    project_id: int = Field(..., description="Target project ID")
    rater_type: str = Field("public", description="Type of rater ('public' or 'recruiter')")
    rater_id: int | None = Field(None, description="Optional ID of rater if registered")
    rating: int = Field(..., ge=1, le=10, description="Rating value from 1 to 10")


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new student",
    description="Registers a new student and optionally their initial repository project.",
)
async def register_student(
    payload: StudentRegisterRequest,
    background_tasks: BackgroundTasks,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Register a new student and optional repository project within a transaction.

    Args:
        payload (StudentRegisterRequest): Registration payload.
        background_tasks (BackgroundTasks): FastAPI BackgroundTasks.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Confirmation status, created student, and optional project record.
    """
    student_data = {
        "name": payload.name,
        "email": payload.email,
        "github_username": payload.github_username,
    }

    try:
        async with conn.transaction():
            student = await create_student(conn, student_data)
            project = None
            if payload.repo_url and payload.repo_url.strip():
                project_data = {
                    "student_id": student["id"],
                    "repo_url": payload.repo_url.strip(),
                    "summary": None,
                    "tags": [],
                    "final_score": None,
                }
                project = await create_project(conn, project_data)
    except asyncpg.UniqueViolationError as err:
        err_msg = str(err.args[0]) if err.args else ""
        if "repo_url" in err_msg or "projects_" in err_msg:
            detail = "Project repository URL already registered"
        else:
            detail = "Student with this email or GitHub username already exists"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    if project:
        background_tasks.add_task(scan_and_evaluate_project_bg, project["id"], project["repo_url"])

    return {
        "status": "success",
        "student": student,
        "project": project,
    }


@router.get(
    "/dashboard",
    summary="Retrieve portfolio projects feed",
    description="Retrieves a paginated list of student portfolio projects sorted by final_score descending.",
)
async def get_dashboard(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Page item limit"),
    search_query: str | None = Query(None, description="Search term for projects or students"),
    min_score: float | None = Query(None, ge=0.0, le=100.0, description="Minimum final_score filter"),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get paginated portfolio feed.

    Args:
        page (int): Page number.
        limit (int): Items per page.
        search_query (str | None): Optional query filter.
        min_score (float | None): Optional minimum score filter.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Paginated dictionary containing items, total count, page, and limit.
    """
    return await get_projects_feed(
        conn,
        page=page,
        limit=limit,
        search_query=search_query,
        min_score=min_score,
    )


@router.post(
    "/rate",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a project rating",
    description="Submits a 1-10 rating for a project with IP rate limiting.",
)
async def rate_project(
    payload: ProjectRatingRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Submit a rating for a project inside a transaction.

    Args:
        payload (ProjectRatingRequest): Rating submission payload.
        request (Request): FastAPI HTTP Request object.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Submitted rating details and updated project final score.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"

    ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()

    rating_data = {
        "project_id": payload.project_id,
        "rater_type": payload.rater_type,
        "rater_id": payload.rater_id,
        "rater_ip_hash": ip_hash,
        "rating": payload.rating,
    }

    try:
        async with conn.transaction():
            rating_record = await add_project_rating(conn, rating_data)
            new_score = await update_project_score(conn, payload.project_id)
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already rated this project today",
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return {
        "status": "success",
        "rating": rating_record,
        "new_final_score": new_score,
    }
