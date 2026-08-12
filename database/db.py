"""Database connection pool management module using asyncpg."""

import logging
import os
from typing import AsyncGenerator

import asyncpg

logger = logging.getLogger("talentcaspian.database")

DB_POOL: asyncpg.Pool | None = None


async def init_db_pool() -> None:
    """Initialize the global PostgreSQL connection pool using asyncpg."""
    global DB_POOL
    if DB_POOL is not None:
        return

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/talentcaspian",
    )
    min_size = int(os.getenv("DB_MIN_SIZE", "5"))
    max_size = int(os.getenv("DB_MAX_SIZE", "20"))

    try:
        DB_POOL = await asyncpg.create_pool(
            dsn=database_url,
            min_size=min_size,
            max_size=max_size,
        )
        logger.info("PostgreSQL database pool initialized successfully.")
    except Exception as exc:
        logger.warning(f"Could not connect to PostgreSQL database pool: {exc}")
        DB_POOL = None


async def close_db_pool() -> None:
    """Close the global PostgreSQL connection pool on shutdown."""
    global DB_POOL
    if DB_POOL:
        await DB_POOL.close()
        DB_POOL = None
        logger.info("PostgreSQL database pool closed.")


async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Dependency for acquiring a database connection from the pool.

    Yields:
        asyncpg.Connection: Active database connection from pool.

    Raises:
        RuntimeError: If database pool is not initialized.
    """
    if DB_POOL is None:
        raise RuntimeError("Database pool is not initialized")
    async with DB_POOL.acquire() as connection:
        yield connection


def is_pool_ready() -> bool:
    """Check if the database connection pool is initialized and active.

    Returns:
        bool: True if DB_POOL is initialized, False otherwise.
    """
    return DB_POOL is not None
