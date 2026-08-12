"""Recruiter API endpoints for TalentCaspian."""

import logging
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from database.db import (
    add_suggestion,
    create_recruiter,
    get_db_connection,
    get_recruiter_by_id,
    get_recruiter_matches,
)

logger = logging.getLogger("talentcaspian.recruiters")

router = APIRouter(prefix="/api", tags=["Recruiters"])


class RecruiterRegisterRequest(BaseModel):
    """Payload schema for recruiter registration."""

    name: str = Field(..., min_length=1, description="Recruiter name")
    email: EmailStr = Field(..., description="Recruiter contact email")
    preferred_channel: Literal["email", "telegram"] = Field(
        "email", description="Preferred contact channel ('email' or 'telegram')"
    )
    telegram_handle: str | None = Field(
        None, description="Telegram handle (required if preferred_channel is 'telegram')"
    )
    preference_filters: dict[str, Any] | None = Field(
        default_factory=dict, description="JSON object containing matching filters e.g. min_score and tech_stack"
    )


class SuggestionCreateRequest(BaseModel):
    """Payload schema for submitting recruiter suggestion on a project."""

    project_id: int = Field(..., description="Project ID being reviewed")
    recruiter_id: int = Field(..., description="Recruiter ID submitting suggestion")
    suggestion_text: str = Field(..., min_length=1, description="Constructive feedback or suggestion text")


@router.post(
    "/recruiter/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new recruiter",
    description="Creates a new recruiter profile with matching preferences and notification channel configuration.",
)
async def register_recruiter(
    payload: RecruiterRegisterRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Register a new recruiter profile.

    Args:
        payload (RecruiterRegisterRequest): Registration details.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Created recruiter record.
    """
    if payload.preferred_channel == "telegram" and not (
        payload.telegram_handle and payload.telegram_handle.strip()
    ):
        raise HTTPException(
            status_code=422,
            detail="telegram_handle is required when preferred_channel is 'telegram'",
        )

    recruiter_data = {
        "name": payload.name,
        "email": payload.email,
        "preferred_channel": payload.preferred_channel,
        "telegram_handle": payload.telegram_handle.strip() if payload.telegram_handle else None,
        "preference_filters": payload.preference_filters or {},
    }

    try:
        recruiter = await create_recruiter(conn, recruiter_data)
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recruiter with this email already exists",
        )

    return recruiter


@router.get(
    "/recruiter/{recruiter_id}",
    summary="Retrieve recruiter profile and matched projects",
    description="Retrieves a recruiter's details and a list of student projects matching their preference_filters.",
)
async def get_recruiter_profile(
    recruiter_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get recruiter profile and matched candidate projects.

    Args:
        recruiter_id (int): Recruiter ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Recruiter info and matched projects list.
    """
    recruiter = await get_recruiter_by_id(conn, recruiter_id)
    if not recruiter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter not found",
        )

    matching_projects = await get_recruiter_matches(conn, recruiter_id)

    return {
        "recruiter": recruiter,
        "matching_projects": matching_projects,
    }


@router.post(
    "/suggest",
    status_code=status.HTTP_201_CREATED,
    summary="Submit recruiter suggestion",
    description="Allows recruiters to submit constructive feedback/suggestions for a specific student project.",
)
async def create_suggestion(
    payload: SuggestionCreateRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Submit project feedback suggestion.

    Args:
        payload (SuggestionCreateRequest): Suggestion payload.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Status confirmation and created suggestion record.
    """
    clean_text = payload.suggestion_text.strip()
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="suggestion_text cannot be empty or blank",
        )

    suggestion_data = {
        "project_id": payload.project_id,
        "recruiter_id": payload.recruiter_id,
        "suggestion_text": clean_text,
    }

    try:
        suggestion = await add_suggestion(conn, suggestion_data)
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referenced project or recruiter not found",
        )

    return {
        "status": "success",
        "suggestion": suggestion,
    }
