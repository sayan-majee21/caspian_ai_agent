"""Public and Student API endpoints for TalentCaspian."""

import hashlib
import logging
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field

import database.db as db_module
from database.db import (
    add_peer_suggestion,
    add_project_rating,
    create_project,
    create_student,
    find_matches,
    get_db_connection,
    get_project_analytics,
    get_project_by_id,
    get_project_commit_logs,
    get_project_peer_suggestions,
    get_project_ratings_history,
    get_project_suggestions,
    get_projects_feed,
    get_recruiter_by_contact,
    get_student_by_email,
    get_student_by_id,
    get_student_profile,
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
@router.get(
    "/feed",
    summary="Retrieve portfolio projects feed (alias)",
    description="Retrieves a paginated list of student portfolio projects sorted by final_score descending with category/tag filtering and preview support.",
)
async def get_dashboard(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Page item limit"),
    search_query: str | None = Query(None, description="Search term for projects or students"),
    tag: str | None = Query(None, description="Tech stack or domain tag filter"),
    min_score: float | None = Query(None, ge=0.0, le=100.0, description="Minimum final_score filter"),
    preview: bool = Query(False, description="Whether to return a light preview card for unauthenticated discovery"),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get paginated portfolio feed.

    Args:
        page (int): Page number.
        limit (int): Items per page.
        search_query (str | None): Optional query filter.
        tag (str | None): Optional tag filter.
        min_score (float | None): Optional minimum score filter.
        preview (bool): Optional preview flag.
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
        tag=tag,
        is_preview=preview,
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


class LoginRequest(BaseModel):
    """Payload schema for student/recruiter authentication."""

    email: EmailStr = Field(..., description="User email address")
    user_type: Literal["student", "recruiter"] = Field(
        "student", description="Account type ('student' or 'recruiter')"
    )
    password: str | None = Field(None, description="Optional password for credentials authentication")


class ProjectAddRequest(BaseModel):
    """Payload schema for adding a new project for an existing registered student."""

    student_id: int = Field(..., description="Registered Student ID")
    repo_url: str = Field(..., min_length=5, description="GitHub repository URL")


class PeerSuggestionCreateRequest(BaseModel):
    """Payload schema for submitting peer feedback on a project."""

    student_id: int | None = Field(None, description="Optional ID of commenting student")
    student_name: str = Field("Anonymous Peer", min_length=1, description="Commentator display name")
    feedback_text: str = Field(..., min_length=1, description="Peer suggestion or constructive feedback")


@router.post(
    "/login",
    summary="User authentication login",
    description="Authenticates a student or recruiter by email.",
)
@router.post(
    "/auth/login",
    summary="User authentication login (alias)",
    description="Authenticates a student or recruiter by email.",
)
async def login_user(
    payload: LoginRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Authenticate student or recruiter user.

    Args:
        payload (LoginRequest): Login credentials.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: User profile and session token.
    """
    if payload.user_type == "student":
        student = await get_student_by_email(conn, payload.email)
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student with email '{payload.email}' not found",
            )
        return {
            "status": "success",
            "user_type": "student",
            "user": student,
            "token": f"stu_session_{student['id']}_{hashlib.md5(payload.email.encode()).hexdigest()[:8]}",
        }
    else:
        recruiter = await get_recruiter_by_contact(conn, payload.email)
        if not recruiter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recruiter with email '{payload.email}' not found",
            )
        return {
            "status": "success",
            "user_type": "recruiter",
            "user": recruiter,
            "token": f"rec_session_{recruiter['id']}_{hashlib.md5(payload.email.encode()).hexdigest()[:8]}",
        }


@router.get(
    "/student/{student_id}",
    summary="Retrieve student profile and portfolio projects",
    description="Retrieves a student's profile, full project portfolio, and aggregate score metrics for Personal Analytics.",
)
async def get_student(
    student_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get student profile and projects.

    Args:
        student_id (int): Student ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Profile details and project list.
    """
    profile = await get_student_profile(conn, student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )
    return profile


@router.post(
    "/projects",
    status_code=status.HTTP_201_CREATED,
    summary="Add a new project for an existing student",
    description="Creates a new project record under an existing student profile and enqueues background AI scanning.",
)
async def add_student_project(
    payload: ProjectAddRequest,
    background_tasks: BackgroundTasks,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Add a project for an already registered student.

    Args:
        payload (ProjectAddRequest): Project submission details.
        background_tasks (BackgroundTasks): Background tasks manager.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Created project record.
    """
    student = await get_student_by_id(conn, payload.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    project_data = {
        "student_id": payload.student_id,
        "repo_url": payload.repo_url.strip(),
        "summary": None,
        "tags": [],
        "final_score": None,
    }
    try:
        project = await create_project(conn, project_data)
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project repository URL already registered",
        )

    background_tasks.add_task(scan_and_evaluate_project_bg, project["id"], project["repo_url"])
    return {
        "status": "success",
        "project": project,
    }


@router.get(
    "/project/{project_id}",
    summary="Retrieve single project detail",
    description="Retrieves full project metadata, author info, recruiter interest count, metric breakdown, and peer suggestions (public-safe view for Search & Feed and recruiter exploration).",
)
async def get_project(
    project_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get public-safe full project details.

    Args:
        project_id (int): Project ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Full project record with metric cards, peer feedback, and recruiter interest count.
    """
    project = await get_project_by_id(conn, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    recruiter_matches = await find_matches(conn, project_id)
    peer_suggs = await get_project_peer_suggestions(conn, project_id)

    metrics = [
        {"name": "Technical Quality", "score": project.get("ai_difficulty") or 0.0},
        {"name": "Code Authenticity", "score": project.get("ai_authenticity") or 0.0},
        {"name": "Project Creativity", "score": project.get("ai_creativity") or 0.0},
    ]

    return {
        "project": project,
        "metrics": metrics,
        "recruiter_interest_count": len(recruiter_matches),
        "peer_suggestions": peer_suggs,
    }


@router.get(
    "/project/{project_id}/analytics",
    summary="Retrieve Personal Analytics for a project",
    description="Retrieves structured analytics bundle including score breakdown, evolution history, recruiter interest, suggestions, and AI next steps for the Personal Analytics tab.",
)
async def get_project_analytics_endpoint(
    project_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get project personal analytics payload.

    Args:
        project_id (int): Project ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Structured analytics dashboard payload.
    """
    analytics = await get_project_analytics(conn, project_id)
    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return analytics


@router.get(
    "/project/{project_id}/ratings",
    summary="Retrieve project ratings history",
    description="Retrieves timestamped ratings history ordered chronologically for trend charting.",
)
async def get_project_ratings(
    project_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get rating trend history for a project.

    Args:
        project_id (int): Project ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Rating history items and statistics.
    """
    project = await get_project_by_id(conn, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    ratings = await get_project_ratings_history(conn, project_id)
    avg_rating = round(sum(r["rating"] for r in ratings) / len(ratings), 2) if ratings else 0.0
    return {
        "project_id": project_id,
        "ratings": ratings,
        "total_ratings": len(ratings),
        "average_rating": avg_rating,
    }


@router.get(
    "/project/{project_id}/commits",
    summary="Retrieve project commit history",
    description="Retrieves recorded commits and change classification history for a project.",
)
async def get_project_commits(
    project_id: int,
    limit: int = Query(50, ge=1, le=200, description="Max commits to return"),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get commit history for a project.

    Args:
        project_id (int): Project ID.
        limit (int): Max commits.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Commit history list and total count.
    """
    project = await get_project_by_id(conn, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    commits = await get_project_commit_logs(conn, project_id, limit=limit)
    return {
        "project_id": project_id,
        "commits": commits,
        "total_commits": len(commits),
    }


@router.get(
    "/project/{project_id}/suggestions",
    summary="Retrieve recruiter suggestions for a project",
    description="Retrieves all recruiter suggestions and feedback notes for a project.",
)
async def get_project_suggestions_endpoint(
    project_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get all recruiter suggestions for a project.

    Args:
        project_id (int): Project ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: List of suggestions.
    """
    project = await get_project_by_id(conn, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    suggestions = await get_project_suggestions(conn, project_id)
    return {
        "project_id": project_id,
        "suggestions": suggestions,
        "total_count": len(suggestions),
    }


@router.get(
    "/project/{project_id}/peer-suggestions",
    summary="Retrieve peer community suggestions",
    description="Retrieves community feedback thread submitted by peers for this project.",
)
async def get_project_peer_suggestions_endpoint(
    project_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get peer community feedback.

    Args:
        project_id (int): Project ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Peer suggestions list and count.
    """
    project = await get_project_by_id(conn, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    peer_suggs = await get_project_peer_suggestions(conn, project_id)
    return {
        "project_id": project_id,
        "peer_suggestions": peer_suggs,
        "total_count": len(peer_suggs),
    }


@router.post(
    "/project/{project_id}/peer-suggestions",
    status_code=status.HTTP_201_CREATED,
    summary="Submit peer community feedback",
    description="Allows other students to submit constructive feedback comments on a project.",
)
async def submit_peer_suggestion(
    project_id: int,
    payload: PeerSuggestionCreateRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Submit peer feedback on a project.

    Args:
        project_id (int): Project ID.
        payload (PeerSuggestionCreateRequest): Feedback payload.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Created peer feedback record.
    """
    project = await get_project_by_id(conn, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    clean_text = payload.feedback_text.strip()
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="feedback_text cannot be empty",
        )

    peer_data = {
        "project_id": project_id,
        "student_id": payload.student_id,
        "student_name": payload.student_name.strip() or "Anonymous Peer",
        "feedback_text": clean_text,
    }
    created = await add_peer_suggestion(conn, peer_data)
    return {
        "status": "success",
        "peer_suggestion": created,
    }
