"""Recruiter API endpoints for TalentCaspian."""

import logging
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from database.db import (
    add_suggestion,
    add_to_cart,
    create_recruiter,
    get_cart_items,
    get_db_connection,
    get_recruiter_by_id,
    get_recruiter_matches,
    get_recruiter_suggestions,
    remove_cart_item_by_id,
    remove_from_cart,
    update_recruiter_preferences,
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


class RecruiterPreferencesUpdateRequest(BaseModel):
    """Payload schema for updating recruiter hiring preferences."""

    preference_filters: dict[str, Any] = Field(
        ..., description="JSON object containing matching filters e.g. min_score and tech_stack"
    )


class CartAddRequest(BaseModel):
    """Payload schema for adding a project to recruiter cart."""

    recruiter_id: int = Field(..., description="Recruiter ID")
    project_id: int = Field(..., description="Project ID to wishlist")


@router.get(
    "/recruiter/{recruiter_id}/suggestions",
    summary="Retrieve recruiter suggestion history",
    description="Retrieves all feedback suggestions submitted by a recruiter, including resolution status and candidate project info for the Suggestion History & Replies tab.",
)
async def get_recruiter_suggestions_endpoint(
    recruiter_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Retrieve recruiter's suggestion history and student response resolution status.

    Args:
        recruiter_id (int): Recruiter ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Recruiter suggestions list and total count.
    """
    recruiter = await get_recruiter_by_id(conn, recruiter_id)
    if not recruiter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter not found",
        )

    suggestions = await get_recruiter_suggestions(conn, recruiter_id)
    return {
        "recruiter_id": recruiter_id,
        "suggestions": suggestions,
        "total_count": len(suggestions),
    }


@router.patch(
    "/recruiter/{recruiter_id}/preferences",
    summary="Update recruiter preferences",
    description="Updates matching preference filters (min_score, tech_stack) for an existing recruiter.",
)
@router.put(
    "/recruiter/{recruiter_id}/preferences",
    summary="Update recruiter preferences (PUT alias)",
    description="Updates matching preference filters (min_score, tech_stack) for an existing recruiter.",
)
async def update_recruiter_preferences_endpoint(
    recruiter_id: int,
    payload: RecruiterPreferencesUpdateRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Update preference filters for a recruiter.

    Args:
        recruiter_id (int): Recruiter ID.
        payload (RecruiterPreferencesUpdateRequest): Updated filters payload.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Updated recruiter record.
    """
    updated = await update_recruiter_preferences(conn, recruiter_id, payload.preference_filters)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter not found",
        )
    return {
        "status": "success",
        "recruiter": updated,
    }


@router.get(
    "/cart/{recruiter_id}",
    summary="Retrieve recruiter cart projects",
    description="Retrieves all candidate projects wishlisted / added to cart by a recruiter.",
)
async def get_recruiter_cart(
    recruiter_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Get recruiter cart items.

    Args:
        recruiter_id (int): Recruiter ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Cart items list and total count.
    """
    recruiter = await get_recruiter_by_id(conn, recruiter_id)
    if not recruiter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter not found",
        )

    cart_items = await get_cart_items(conn, recruiter_id)
    return {
        "recruiter_id": recruiter_id,
        "cart_items": cart_items,
        "total_count": len(cart_items),
    }


@router.post(
    "/cart",
    status_code=status.HTTP_201_CREATED,
    summary="Add project to recruiter cart",
    description="Wishlists/adds a student project into a recruiter's cart.",
)
async def add_project_to_cart(
    payload: CartAddRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Add a project to cart.

    Args:
        payload (CartAddRequest): Recruiter and project ID payload.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Added cart item details.
    """
    recruiter = await get_recruiter_by_id(conn, payload.recruiter_id)
    if not recruiter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter not found",
        )

    try:
        cart_item = await add_to_cart(conn, payload.recruiter_id, payload.project_id)
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return {
        "status": "success",
        "cart_item": cart_item,
    }


@router.delete(
    "/cart/{item_id}",
    summary="Remove item from recruiter cart by item ID",
    description="Deletes a project entry from cart by its cart item ID.",
)
async def delete_cart_item(
    item_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Delete cart item by ID.

    Args:
        item_id (int): Cart item ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Deletion status confirmation.
    """
    deleted = await remove_cart_item_by_id(conn, item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )
    return {
        "status": "success",
        "message": f"Cart item #{item_id} removed successfully",
    }


@router.delete(
    "/cart/{recruiter_id}/{project_id}",
    summary="Remove project from recruiter cart",
    description="Removes a specific project from a recruiter's cart by recruiter ID and project ID.",
)
async def remove_project_from_cart(
    recruiter_id: int,
    project_id: int,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> dict[str, Any]:
    """Remove project from recruiter cart.

    Args:
        recruiter_id (int): Recruiter ID.
        project_id (int): Project ID.
        conn (asyncpg.Connection): Active database connection.

    Returns:
        dict[str, Any]: Deletion status confirmation.
    """
    deleted = await remove_from_cart(conn, recruiter_id, project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not in recruiter's cart",
        )
    return {
        "status": "success",
        "message": f"Project #{project_id} removed from recruiter #{recruiter_id} cart",
    }
