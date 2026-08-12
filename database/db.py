"""Database connection pool management and Data Access Objects (DAOs) using asyncpg."""

import json
import logging
import os
from typing import Any, AsyncGenerator

import asyncpg

from database.scoring import calculate_final_score

logger = logging.getLogger("talentcaspian.database")

DB_POOL: asyncpg.Pool | None = None


# ---------------------------------------------------------------------------
# Schema DDL Definitions
# ---------------------------------------------------------------------------
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    github_username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    repo_url TEXT UNIQUE NOT NULL,
    summary TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    ai_difficulty FLOAT,
    ai_authenticity FLOAT,
    ai_creativity FLOAT,
    ai_score FLOAT,
    final_score FLOAT,
    last_scanned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recruiters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    preferred_channel VARCHAR(50) DEFAULT 'email',
    telegram_handle VARCHAR(255),
    preference_filters JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_ratings (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rater_type VARCHAR(50) NOT NULL,
    rater_id INTEGER,
    rater_ip_hash VARCHAR(64),
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rating_per_ip_per_day
    ON project_ratings (project_id, rater_ip_hash, ((created_at AT TIME ZONE 'UTC')::date))
    WHERE rater_ip_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS suggestions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    recruiter_id INTEGER NOT NULL REFERENCES recruiters(id) ON DELETE CASCADE,
    suggestion_text TEXT NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notification_logs (
    id SERIAL PRIMARY KEY,
    recruiter_id INTEGER NOT NULL REFERENCES recruiters(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    channel VARCHAR(50),
    is_followup BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processed_deliveries (
    delivery_id VARCHAR(255) PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_student_id ON projects(student_id);
CREATE INDEX IF NOT EXISTS idx_projects_tags ON projects USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_project_ratings_project_id ON project_ratings(project_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_project_id ON suggestions(project_id);
CREATE INDEX IF NOT EXISTS idx_recruiters_preference_filters ON recruiters USING GIN (preference_filters);
CREATE INDEX IF NOT EXISTS idx_notification_logs_recruiter_project ON notification_logs(recruiter_id, project_id, sent_at DESC);
"""


async def init_db_schema(pool: asyncpg.Pool) -> None:
    """Initialize relational database tables and indexes if they do not exist.

    Args:
        pool (asyncpg.Pool): Active asyncpg connection pool.
    """
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(CREATE_TABLES_SQL)
    logger.info("Database schema and indexes initialized successfully.")


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
        try:
            await init_db_schema(DB_POOL)
        except Exception as schema_exc:
            logger.warning(f"Could not initialize database schema: {schema_exc}")
    except Exception as exc:
        logger.warning(f"Could not connect to PostgreSQL database pool: {exc}")
        DB_POOL = None


async def close_db_pool() -> None:
    """Close the global PostgreSQL connection pool on shutdown safely."""
    global DB_POOL
    if DB_POOL:
        try:
            await DB_POOL.close()
            logger.info("PostgreSQL database pool closed.")
        finally:
            DB_POOL = None


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


# ---------------------------------------------------------------------------
# Data Access Objects (DAOs) / Query Helpers
# ---------------------------------------------------------------------------


async def create_student(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, student_data: dict[str, Any]
) -> dict[str, Any]:
    """Insert a new student record into the database.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        student_data (dict[str, Any]): Dictionary containing name, email, github_username.

    Returns:
        dict[str, Any]: Created student record.
    """
    sql = """
    INSERT INTO students (name, email, github_username)
    VALUES ($1, $2, $3)
    RETURNING id, name, email, github_username, created_at;
    """
    row = await conn_or_pool.fetchrow(
        sql,
        student_data["name"],
        student_data["email"],
        student_data["github_username"],
    )
    return dict(row) if row else {}


async def get_student_by_email_or_username(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, email: str, github_username: str
) -> dict[str, Any] | None:
    """Find student by email or GitHub username.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        email (str): Student email.
        github_username (str): GitHub username.

    Returns:
        dict[str, Any] | None: Student record if found, else None.
    """
    sql = """
    SELECT id, name, email, github_username, created_at
    FROM students
    WHERE email = $1 OR github_username = $2;
    """
    row = await conn_or_pool.fetchrow(sql, email, github_username)
    return dict(row) if row else None


async def create_project(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_data: dict[str, Any]
) -> dict[str, Any]:
    """Insert a new project record into the database.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_data (dict[str, Any]): Project data (student_id, repo_url, optional summary, tags).

    Returns:
        dict[str, Any]: Created project record.
    """
    tags_json = json.dumps(project_data.get("tags", []))
    sql = """
    INSERT INTO projects (student_id, repo_url, summary, tags, final_score)
    VALUES ($1, $2, $3, $4::jsonb, $5)
    RETURNING id, student_id, repo_url, summary, tags, ai_difficulty, ai_authenticity,
              ai_creativity, ai_score, final_score, last_scanned_at, created_at;
    """
    row = await conn_or_pool.fetchrow(
        sql,
        project_data["student_id"],
        project_data["repo_url"],
        project_data.get("summary"),
        tags_json,
        project_data.get("final_score"),
    )
    if row:
        res = dict(row)
        if isinstance(res.get("tags"), str):
            res["tags"] = json.loads(res["tags"])
        return res
    return {}


async def get_projects_feed(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool,
    page: int = 1,
    limit: int = 10,
    search_query: str | None = None,
    min_score: float | None = None,
) -> dict[str, Any]:
    """Retrieve paginated portfolio projects feed ordered by final_score descending.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        page (int): Page number (1-indexed).
        limit (int): Items per page.
        search_query (str | None): Optional search term.
        min_score (float | None): Optional minimum final score filter.

    Returns:
        dict[str, Any]: Paginated dictionary containing items, total count, page, and limit.
    """
    offset = (page - 1) * limit
    conditions = ["1=1"]
    args: list[Any] = []
    arg_idx = 1

    if min_score is not None:
        conditions.append(f"COALESCE(p.final_score, 0) >= ${arg_idx}")
        args.append(min_score)
        arg_idx += 1

    if search_query and search_query.strip():
        term = f"%{search_query.strip()}%"
        conditions.append(
            f"(p.summary ILIKE ${arg_idx} OR p.repo_url ILIKE ${arg_idx} OR "
            f"s.name ILIKE ${arg_idx} OR s.github_username ILIKE ${arg_idx} OR "
            f"p.tags::text ILIKE ${arg_idx})"
        )
        args.append(term)
        arg_idx += 1

    where_clause = " AND ".join(conditions)

    count_sql = f"""
    SELECT COUNT(*)
    FROM projects p
    JOIN students s ON p.student_id = s.id
    WHERE {where_clause};
    """

    feed_sql = f"""
    SELECT p.id, p.student_id, p.repo_url, p.summary, p.tags, p.ai_difficulty,
           p.ai_authenticity, p.ai_creativity, p.ai_score, p.final_score,
           p.last_scanned_at, p.created_at,
           s.name as student_name, s.github_username, s.email as student_email,
           (SELECT COUNT(*) FROM project_ratings pr WHERE pr.project_id = p.id) as ratings_count
    FROM projects p
    JOIN students s ON p.student_id = s.id
    WHERE {where_clause}
    ORDER BY p.final_score DESC NULLS LAST, p.created_at DESC
    LIMIT ${arg_idx} OFFSET ${arg_idx + 1};
    """

    total = await conn_or_pool.fetchval(count_sql, *args)
    rows = await conn_or_pool.fetch(feed_sql, *args, limit, offset)
    items = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("tags"), str):
            item["tags"] = json.loads(item["tags"])
        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
    }


async def add_project_rating(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, rating_data: dict[str, Any]
) -> dict[str, Any]:
    """Submit a rating for a project with IP-based uniqueness constraint.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        rating_data (dict[str, Any]): Rating metadata.

    Returns:
        dict[str, Any]: Created rating record.
    """
    sql = """
    INSERT INTO project_ratings (project_id, rater_type, rater_id, rater_ip_hash, rating)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING id, project_id, rater_type, rater_id, rater_ip_hash, rating, created_at;
    """
    row = await conn_or_pool.fetchrow(
        sql,
        rating_data["project_id"],
        rating_data.get("rater_type", "public"),
        rating_data.get("rater_id"),
        rating_data.get("rater_ip_hash"),
        rating_data["rating"],
    )
    return dict(row) if row else {}


async def update_project_score(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> float:
    """Recalculate and update the final_score of a project using Bayesian average.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): ID of the project to update.

    Returns:
        float: Newly calculated final_score.
    """
    ai_score = await conn_or_pool.fetchval(
        "SELECT ai_score FROM projects WHERE id = $1;", project_id
    )
    rating_rows = await conn_or_pool.fetch(
        "SELECT rating FROM project_ratings WHERE project_id = $1;",
        project_id,
    )
    ratings = [r["rating"] for r in rating_rows]
    new_final_score = calculate_final_score(ai_score, ratings)

    await conn_or_pool.execute(
        "UPDATE projects SET final_score = $1 WHERE id = $2;",
        new_final_score,
        project_id,
    )
    return new_final_score


async def update_project_ai_scores(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool,
    project_id: int,
    ai_difficulty: float,
    ai_authenticity: float,
    ai_creativity: float,
    ai_score: float,
    tags: list[str],
    summary: str,
) -> dict[str, Any]:
    """Update AI evaluation scores, tags, and summary for a project, then recalculate final_score.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.
        ai_difficulty (float): Difficulty score (0-100).
        ai_authenticity (float): Authenticity score (0-100).
        ai_creativity (float): Creativity score (0-100).
        ai_score (float): Overall AI score (0-100).
        tags (list[str]): List of tech stack tags.
        summary (str): AI generated summary.

    Returns:
        dict[str, Any]: Updated project record.
    """
    tags_json = json.dumps(tags)
    sql = """
    UPDATE projects
    SET ai_difficulty = $1,
        ai_authenticity = $2,
        ai_creativity = $3,
        ai_score = $4,
        tags = $5::jsonb,
        summary = $6,
        last_scanned_at = CURRENT_TIMESTAMP
    WHERE id = $7;
    """
    await conn_or_pool.execute(
        sql,
        ai_difficulty,
        ai_authenticity,
        ai_creativity,
        ai_score,
        tags_json,
        summary,
        project_id,
    )

    await update_project_score(conn_or_pool, project_id)

    row = await conn_or_pool.fetchrow("SELECT * FROM projects WHERE id = $1;", project_id)
    if row:
        res = dict(row)
        if isinstance(res.get("tags"), str):
            res["tags"] = json.loads(res["tags"])
        return res
    return {}


async def create_recruiter(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_data: dict[str, Any]
) -> dict[str, Any]:
    """Insert a new recruiter record into the database.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_data (dict[str, Any]): Recruiter record attributes.

    Returns:
        dict[str, Any]: Created recruiter record.
    """
    filters_json = json.dumps(recruiter_data.get("preference_filters", {}))
    sql = """
    INSERT INTO recruiters (name, email, preferred_channel, telegram_handle, preference_filters)
    VALUES ($1, $2, $3, $4, $5::jsonb)
    RETURNING id, name, email, preferred_channel, telegram_handle, preference_filters, created_at;
    """
    row = await conn_or_pool.fetchrow(
        sql,
        recruiter_data["name"],
        recruiter_data["email"],
        recruiter_data.get("preferred_channel", "email"),
        recruiter_data.get("telegram_handle"),
        filters_json,
    )
    if row:
        res = dict(row)
        if isinstance(res.get("preference_filters"), str):
            res["preference_filters"] = json.loads(res["preference_filters"])
        return res
    return {}


async def get_recruiter_by_id(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_id: int
) -> dict[str, Any] | None:
    """Retrieve recruiter by ID.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.

    Returns:
        dict[str, Any] | None: Recruiter record if found, else None.
    """
    sql = """
    SELECT id, name, email, preferred_channel, telegram_handle, preference_filters, created_at
    FROM recruiters
    WHERE id = $1;
    """
    row = await conn_or_pool.fetchrow(sql, recruiter_id)
    if row:
        res = dict(row)
        if isinstance(res.get("preference_filters"), str):
            res["preference_filters"] = json.loads(res["preference_filters"])
        return res
    return None


async def get_recruiter_matches(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_id: int
) -> list[dict[str, Any]]:
    """Get candidate projects matching a recruiter's preference_filters.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.

    Returns:
        list[dict[str, Any]]: Matching projects list.
    """
    sql = """
    SELECT p.id, p.student_id, p.repo_url, p.summary, p.tags, p.ai_difficulty,
           p.ai_authenticity, p.ai_creativity, p.ai_score, p.final_score,
           p.last_scanned_at, p.created_at,
           s.name as student_name, s.github_username, s.email as student_email
    FROM projects p
    JOIN students s ON p.student_id = s.id, recruiters r
    WHERE r.id = $1
      AND COALESCE(p.final_score, 0) >= COALESCE((r.preference_filters->>'min_score')::float, 0)
      AND (
        r.preference_filters->'tech_stack' IS NULL 
        OR jsonb_typeof(r.preference_filters->'tech_stack') != 'array'
        OR r.preference_filters->'tech_stack' = '[]'::jsonb
        OR jsonb_array_length(r.preference_filters->'tech_stack') = 0
        OR EXISTS (
          SELECT 1 
          FROM jsonb_array_elements_text(p.tags) tag
          WHERE tag = ANY (
            SELECT jsonb_array_elements_text(r.preference_filters->'tech_stack')
          )
        )
      )
    ORDER BY p.final_score DESC NULLS LAST;
    """
    rows = await conn_or_pool.fetch(sql, recruiter_id)
    items = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("tags"), str):
            item["tags"] = json.loads(item["tags"])
        items.append(item)
    return items


async def find_matches(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> list[dict[str, Any]]:
    """Get candidate recruiters matching a specific project's score and tech stack tags.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.

    Returns:
        list[dict[str, Any]]: Matching recruiters list.
    """
    sql = """
    SELECT r.id, r.name, r.email, r.preferred_channel, r.telegram_handle, r.preference_filters, r.created_at
    FROM recruiters r, projects p
    WHERE p.id = $1
      AND COALESCE(p.final_score, 0) >= COALESCE((r.preference_filters->>'min_score')::float, 0)
      AND (
        r.preference_filters->'tech_stack' IS NULL
        OR jsonb_typeof(r.preference_filters->'tech_stack') != 'array'
        OR r.preference_filters->'tech_stack' = '[]'::jsonb
        OR jsonb_array_length(r.preference_filters->'tech_stack') = 0
        OR EXISTS (
          SELECT 1
          FROM jsonb_array_elements_text(p.tags) tag
          WHERE tag = ANY (
            SELECT jsonb_array_elements_text(r.preference_filters->'tech_stack')
          )
        )
      );
    """
    rows = await conn_or_pool.fetch(sql, project_id)
    items = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("preference_filters"), str):
            item["preference_filters"] = json.loads(item["preference_filters"])
        items.append(item)
    return items


# Alias for find_matches
get_project_matches = find_matches


async def add_suggestion(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, suggestion_data: dict[str, Any]
) -> dict[str, Any]:
    """Insert a recruiter suggestion feedback for a project.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        suggestion_data (dict[str, Any]): Contains project_id, recruiter_id, suggestion_text.

    Returns:
        dict[str, Any]: Created suggestion record.
    """
    sql = """
    INSERT INTO suggestions (project_id, recruiter_id, suggestion_text)
    VALUES ($1, $2, $3)
    RETURNING id, project_id, recruiter_id, suggestion_text, resolved, created_at;
    """
    row = await conn_or_pool.fetchrow(
        sql,
        suggestion_data["project_id"],
        suggestion_data["recruiter_id"],
        suggestion_data["suggestion_text"],
    )
    return dict(row) if row else {}


async def has_recent_notification(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool,
    recruiter_id: int,
    project_id: int,
    within_days: int = 7,
) -> bool:
    """Check if a notification was sent to a recruiter for a project within a given number of days.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.
        project_id (int): Project ID.
        within_days (int): Time window in days. Defaults to 7.

    Returns:
        bool: True if recent notification exists, False otherwise.
    """
    sql = """
    SELECT EXISTS (
        SELECT 1
        FROM notification_logs
        WHERE recruiter_id = $1
          AND project_id = $2
          AND sent_at >= CURRENT_TIMESTAMP - ($3 || ' days')::INTERVAL
    );
    """
    val = await conn_or_pool.fetchval(sql, recruiter_id, project_id, str(within_days))
    return bool(val)


async def is_delivery_processed(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, delivery_id: str
) -> bool:
    """Check if a webhook delivery ID has already been processed.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        delivery_id (str): Unique GitHub delivery UUID.

    Returns:
        bool: True if already processed, False otherwise.
    """
    sql = "SELECT EXISTS (SELECT 1 FROM processed_deliveries WHERE delivery_id = $1);"
    val = await conn_or_pool.fetchval(sql, delivery_id)
    return bool(val)


async def record_delivery_processed(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, delivery_id: str
) -> None:
    """Record a webhook delivery ID as processed.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        delivery_id (str): Unique GitHub delivery UUID.
    """
    sql = """
    INSERT INTO processed_deliveries (delivery_id)
    VALUES ($1)
    ON CONFLICT (delivery_id) DO NOTHING;
    """
    await conn_or_pool.execute(sql, delivery_id)


async def get_project_by_repo_url(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, repo_url: str
) -> dict[str, Any] | None:
    """Retrieve a project record by exact repository URL or normalized URL match.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        repo_url (str): GitHub repository URL or SSH/clone URL.

    Returns:
        dict[str, Any] | None: Project record if found, None otherwise.
    """
    clean_url = repo_url.rstrip("/").removesuffix(".git")
    sql = """
    SELECT * FROM projects
    WHERE LOWER(repo_url) = LOWER($1)
       OR LOWER(repo_url) = LOWER($2)
       OR LOWER(repo_url) LIKE LOWER($3);
    """
    row = await conn_or_pool.fetchrow(sql, repo_url, clean_url, f"%{clean_url}%")
    if not row:
        return None
    res = dict(row)
    if isinstance(res.get("tags"), str):
        res["tags"] = json.loads(res["tags"])
    return res


async def get_unresolved_suggestions(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> list[dict[str, Any]]:
    """Retrieve all unresolved suggestions for a specific project.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.

    Returns:
        list[dict[str, Any]]: List of unresolved suggestion records.
    """
    sql = """
    SELECT id, project_id, recruiter_id, suggestion_text, resolved, created_at
    FROM suggestions
    WHERE project_id = $1 AND resolved = FALSE
    ORDER BY created_at ASC;
    """
    rows = await conn_or_pool.fetch(sql, project_id)
    return [dict(r) for r in rows]


async def mark_suggestion_resolved(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, suggestion_id: int
) -> dict[str, Any] | None:
    """Mark a recruiter suggestion as resolved.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        suggestion_id (int): Suggestion ID.

    Returns:
        dict[str, Any] | None: Updated suggestion record.
    """
    sql = """
    UPDATE suggestions
    SET resolved = TRUE
    WHERE id = $1
    RETURNING id, project_id, recruiter_id, suggestion_text, resolved, created_at;
    """
    row = await conn_or_pool.fetchrow(sql, suggestion_id)
    return dict(row) if row else None

