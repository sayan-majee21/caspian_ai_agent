"""Matching Engine for TalentCaspian Agent 2.

Identifies optimal intersections between project characteristics (tags, final_score)
and recruiter preference filters (JSONB).
"""

import logging
from typing import Any

import asyncpg

from database.db import get_project_matches, get_recruiter_matches

logger = logging.getLogger("talentcaspian.matching_engine")


async def find_matches(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> list[dict[str, Any]]:
    """Identify optimal recruiters matching a specific project ID.

    Queries recruiters whose preference_filters JSONB criteria (min_score and tech_stack tags)
    are satisfied by the project's final_score and tags.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID to find matching recruiters for.

    Returns:
        list[dict[str, Any]]: List of matching recruiter dictionaries.
    """
    logger.info(f"Finding recruiter matches for project_id={project_id}")
    return await get_project_matches(conn_or_pool, project_id)


async def find_candidate_projects(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_id: int
) -> list[dict[str, Any]]:
    """Identify candidate projects matching a specific recruiter ID.

    Queries projects whose final_score and tags satisfy the recruiter's preference_filters JSONB.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID to find candidate projects for.

    Returns:
        list[dict[str, Any]]: List of matching project dictionaries.
    """
    logger.info(f"Finding candidate projects for recruiter_id={recruiter_id}")
    return await get_recruiter_matches(conn_or_pool, recruiter_id)
