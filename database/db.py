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
    password_hash VARCHAR(255),
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
    password_hash VARCHAR(255),
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

CREATE TABLE IF NOT EXISTS commit_logs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    commit_hash VARCHAR(64),
    commit_message TEXT NOT NULL,
    author_name VARCHAR(255),
    commit_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    classification VARCHAR(50) DEFAULT 'Minor',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS peer_suggestions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    student_id INTEGER REFERENCES students(id) ON DELETE SET NULL,
    student_name VARCHAR(255),
    feedback_text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cart_items (
    id SERIAL PRIMARY KEY,
    recruiter_id INTEGER NOT NULL REFERENCES recruiters(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (recruiter_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_projects_student_id ON projects(student_id);
CREATE INDEX IF NOT EXISTS idx_projects_tags ON projects USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_project_ratings_project_id ON project_ratings(project_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_project_id ON suggestions(project_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_recruiter_id ON suggestions(recruiter_id);
CREATE INDEX IF NOT EXISTS idx_recruiters_preference_filters ON recruiters USING GIN (preference_filters);
CREATE INDEX IF NOT EXISTS idx_notification_logs_recruiter_project ON notification_logs(recruiter_id, project_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_commit_logs_project_id ON commit_logs(project_id, commit_date DESC);
CREATE INDEX IF NOT EXISTS idx_peer_suggestions_project_id ON peer_suggestions(project_id);
CREATE INDEX IF NOT EXISTS idx_cart_items_recruiter_id ON cart_items(recruiter_id);
"""


SCHEMA_MIGRATIONS_SQL = """
ALTER TABLE students ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE recruiters ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
"""


async def init_db_schema(pool: asyncpg.Pool) -> None:
    """Initialize relational database tables and indexes if they do not exist.

    Args:
        pool (asyncpg.Pool): Active asyncpg connection pool.
    """
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(CREATE_TABLES_SQL)
            await connection.execute(SCHEMA_MIGRATIONS_SQL)
    logger.info("Database schema, tables, columns, and indexes initialized successfully.")


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
    WHERE LOWER(email) = LOWER($1) OR LOWER(github_username) = LOWER($2);
    """
    row = await conn_or_pool.fetchrow(sql, email.strip(), github_username.strip())
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
    tag: str | None = None,
    is_preview: bool = False,
) -> dict[str, Any]:
    """Retrieve paginated portfolio projects feed ordered by final_score descending.

    Supports public preview mode (for non-logged-in discovery) and tag filtering.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        page (int): Page number (1-indexed).
        limit (int): Items per page.
        search_query (str | None): Optional search term.
        min_score (float | None): Optional minimum final score filter.
        tag (str | None): Optional tag filter.
        is_preview (bool): If True, returns minimal preview cards without private details.

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

    if tag and tag.strip():
        conditions.append(
            f"EXISTS (SELECT 1 FROM jsonb_array_elements_text(p.tags) t WHERE LOWER(t) = LOWER(${arg_idx}))"
        )
        args.append(tag.strip())
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

        repo_url = item.get("repo_url", "")
        project_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git") if repo_url else "Project"
        item["project_name"] = project_name

        if is_preview:
            items.append({
                "id": item["id"],
                "project_name": project_name,
                "summary": item.get("summary") or "Project summary available upon student login.",
                "tags": item.get("tags") or [],
                "final_score": item.get("final_score"),
                "preview_only": True,
            })
        else:
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
    sql = r"""
    SELECT p.id, p.student_id, p.repo_url, p.summary, p.tags, p.ai_difficulty,
           p.ai_authenticity, p.ai_creativity, p.ai_score, p.final_score,
           p.last_scanned_at, p.created_at,
           s.name as student_name, s.github_username, s.email as student_email
    FROM projects p
    JOIN students s ON p.student_id = s.id, recruiters r
    WHERE r.id = $1
      AND COALESCE(p.final_score, 0) >= CASE 
          WHEN (r.preference_filters->>'min_score') ~ '^[0-9]+(\.[0-9]+)?$' 
          THEN (r.preference_filters->>'min_score')::float 
          ELSE 0.0 
      END
      AND (
        r.preference_filters->'tech_stack' IS NULL 
        OR jsonb_typeof(r.preference_filters->'tech_stack') != 'array'
        OR r.preference_filters->'tech_stack' = '[]'::jsonb
        OR jsonb_array_length(r.preference_filters->'tech_stack') = 0
        OR (
          p.tags IS NOT NULL
          AND jsonb_typeof(p.tags) = 'array'
          AND jsonb_array_length(p.tags) > 0
          AND EXISTS (
            SELECT 1 
            FROM jsonb_array_elements_text(p.tags) tag
            WHERE LOWER(tag) = ANY (
              SELECT LOWER(t) FROM jsonb_array_elements_text(r.preference_filters->'tech_stack') t
            )
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
    sql = r"""
    SELECT r.id, r.name, r.email, r.preferred_channel, r.telegram_handle, r.preference_filters, r.created_at
    FROM recruiters r, projects p
    WHERE p.id = $1
      AND COALESCE(p.final_score, 0) >= CASE 
          WHEN (r.preference_filters->>'min_score') ~ '^[0-9]+(\.[0-9]+)?$' 
          THEN (r.preference_filters->>'min_score')::float 
          ELSE 0.0 
      END
      AND (
        r.preference_filters->'tech_stack' IS NULL
        OR jsonb_typeof(r.preference_filters->'tech_stack') != 'array'
        OR r.preference_filters->'tech_stack' = '[]'::jsonb
        OR jsonb_array_length(r.preference_filters->'tech_stack') = 0
        OR (
          p.tags IS NOT NULL
          AND jsonb_typeof(p.tags) = 'array'
          AND jsonb_array_length(p.tags) > 0
          AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(p.tags) tag
            WHERE LOWER(tag) = ANY (
              SELECT LOWER(t) FROM jsonb_array_elements_text(r.preference_filters->'tech_stack') t
            )
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
    clean_url = repo_url.rstrip("/").removesuffix(".git").lower()
    sql = """
    SELECT * FROM projects
    WHERE LOWER(repo_url) = $1
       OR LOWER(repo_url) = $1 || '.git'
       OR LOWER(repo_url) = $1 || '/'
       OR LOWER(repo_url) = $1 || '/.git';
    """
    row = await conn_or_pool.fetchrow(sql, clean_url)
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


async def get_project_by_id(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> dict[str, Any] | None:
    """Retrieve a project record with student metadata by project ID.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.

    Returns:
        dict[str, Any] | None: Project record if found, else None.
    """
    sql = """
    SELECT p.id, p.student_id, p.repo_url, p.summary, p.tags, p.ai_difficulty,
           p.ai_authenticity, p.ai_creativity, p.ai_score, p.final_score,
           p.last_scanned_at, p.created_at,
           s.name as student_name, s.github_username, s.email as student_email
    FROM projects p
    LEFT JOIN students s ON p.student_id = s.id
    WHERE p.id = $1;
    """
    row = await conn_or_pool.fetchrow(sql, project_id)
    if row:
        res = dict(row)
        if isinstance(res.get("tags"), str):
            res["tags"] = json.loads(res["tags"])
        return res
    return None


async def create_notification_log(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool,
    recruiter_id: int,
    project_id: int,
    channel: str,
    is_followup: bool = False,
) -> dict[str, Any]:
    """Insert a record into notification_logs table.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.
        project_id (int): Project ID.
        channel (str): Preferred channel used for notification ('email', 'telegram', etc.).
        is_followup (bool): Whether this notification is a follow-up outreach. Defaults to False.

    Returns:
        dict[str, Any]: Created notification log record.
    """
    sql = """
    INSERT INTO notification_logs (recruiter_id, project_id, channel, is_followup)
    VALUES ($1, $2, $3, $4)
    RETURNING id, recruiter_id, project_id, channel, is_followup, sent_at;
    """
    row = await conn_or_pool.fetchrow(sql, recruiter_id, project_id, channel, is_followup)
    return dict(row) if row else {}


async def get_recruiter_by_contact(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, contact_info: str
) -> dict[str, Any] | None:
    """Find recruiter by email address or Telegram handle.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        contact_info (str): Recruiter email address or Telegram handle.

    Returns:
        dict[str, Any] | None: Recruiter record if found, else None.
    """
    if not contact_info:
        return None

    clean_info = str(contact_info).strip()
    clean_no_at = clean_info.lstrip("@")
    clean_with_at = f"@{clean_no_at}"

    sql = """
    SELECT id, name, email, preferred_channel, telegram_handle, preference_filters, created_at
    FROM recruiters
    WHERE LOWER(email) = LOWER($1)
       OR LOWER(telegram_handle) = LOWER($1)
       OR LOWER(telegram_handle) = LOWER($2)
       OR LOWER(telegram_handle) = LOWER($3);
    """
    row = await conn_or_pool.fetchrow(sql, clean_info, clean_no_at, clean_with_at)
    if row:
        res = dict(row)
        if isinstance(res.get("preference_filters"), str):
            res["preference_filters"] = json.loads(res["preference_filters"])
        return res
    return None


async def get_latest_notified_project_for_recruiter(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_id: int
) -> int | None:
    """Retrieve the project ID of the most recent notification log for a recruiter.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.

    Returns:
        int | None: Latest notified project ID if found, else None.
    """
    sql = """
    SELECT project_id
    FROM notification_logs
    WHERE recruiter_id = $1
    ORDER BY sent_at DESC, id DESC
    LIMIT 1;
    """
    val = await conn_or_pool.fetchval(sql, recruiter_id)
    return int(val) if val is not None else None


async def get_student_by_id(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, student_id: int
) -> dict[str, Any] | None:
    """Retrieve a student record by student ID.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        student_id (int): Student ID.

    Returns:
        dict[str, Any] | None: Student record if found, else None.
    """
    sql = """
    SELECT id, name, email, github_username, created_at
    FROM students
    WHERE id = $1;
    """
    row = await conn_or_pool.fetchrow(sql, student_id)
    return dict(row) if row else None


async def get_student_by_email(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, email: str
) -> dict[str, Any] | None:
    """Retrieve a student record by email address.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        email (str): Student email.

    Returns:
        dict[str, Any] | None: Student record if found, else None.
    """
    sql = """
    SELECT id, name, email, github_username, created_at
    FROM students
    WHERE LOWER(email) = LOWER($1);
    """
    row = await conn_or_pool.fetchrow(sql, email.strip())
    return dict(row) if row else None


async def get_student_projects(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, student_id: int
) -> list[dict[str, Any]]:
    """Retrieve all projects belonging to a specific student.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        student_id (int): Student ID.

    Returns:
        list[dict[str, Any]]: List of project dictionaries.
    """
    sql = """
    SELECT id, student_id, repo_url, summary, tags, ai_difficulty,
           ai_authenticity, ai_creativity, ai_score, final_score,
           last_scanned_at, created_at
    FROM projects
    WHERE student_id = $1
    ORDER BY final_score DESC NULLS LAST, id DESC;
    """
    rows = await conn_or_pool.fetch(sql, student_id)
    items = []
    for r in rows:
        item = dict(r)
        if isinstance(item.get("tags"), str):
            item["tags"] = json.loads(item["tags"])
        items.append(item)
    return items


async def get_student_profile(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, student_id: int
) -> dict[str, Any] | None:
    """Retrieve a student's full profile including all projects and summary metrics.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        student_id (int): Student ID.

    Returns:
        dict[str, Any] | None: Full student profile dictionary or None.
    """
    student = await get_student_by_id(conn_or_pool, student_id)
    if not student:
        return None
    projects = await get_student_projects(conn_or_pool, student_id)
    scores = [p["final_score"] for p in projects if p.get("final_score") is not None]
    top_score = max(scores, default=0.0)
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    return {
        "student": student,
        "projects": projects,
        "total_projects": len(projects),
        "top_score": top_score,
        "average_score": avg_score,
    }


async def get_project_ratings_history(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> list[dict[str, Any]]:
    """Retrieve timestamped rating history for a project ordered chronologically.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.

    Returns:
        list[dict[str, Any]]: List of rating records.
    """
    sql = """
    SELECT id, project_id, rater_type, rater_id, rating, created_at
    FROM project_ratings
    WHERE project_id = $1
    ORDER BY created_at ASC, id ASC;
    """
    rows = await conn_or_pool.fetch(sql, project_id)
    return [dict(r) for r in rows]


async def get_project_suggestions(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> list[dict[str, Any]]:
    """Retrieve all recruiter suggestions for a project with recruiter details.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.

    Returns:
        list[dict[str, Any]]: List of suggestion dictionaries.
    """
    sql = """
    SELECT s.id, s.project_id, s.recruiter_id, s.suggestion_text, s.resolved, s.created_at,
           r.name as recruiter_name, r.email as recruiter_email, r.preferred_channel
    FROM suggestions s
    JOIN recruiters r ON s.recruiter_id = r.id
    WHERE s.project_id = $1
    ORDER BY s.created_at DESC, s.id DESC;
    """
    rows = await conn_or_pool.fetch(sql, project_id)
    items = []
    for r in rows:
        item = dict(r)
        item["status"] = "Resolved" if item.get("resolved") else "Open"
        item["priority"] = "High" if not item.get("resolved") else "Resolved"
        items.append(item)
    return items


async def get_recruiter_suggestions(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_id: int
) -> list[dict[str, Any]]:
    """Retrieve all suggestions submitted by a recruiter, with project & student details.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.

    Returns:
        list[dict[str, Any]]: List of recruiter's suggestion history records.
    """
    sql = """
    SELECT s.id, s.project_id, s.recruiter_id, s.suggestion_text, s.resolved, s.created_at,
           p.repo_url, p.summary as project_summary, p.final_score as project_score,
           st.name as student_name, st.github_username, st.email as student_email
    FROM suggestions s
    JOIN projects p ON s.project_id = p.id
    JOIN students st ON p.student_id = st.id
    WHERE s.recruiter_id = $1
    ORDER BY s.created_at DESC, s.id DESC;
    """
    rows = await conn_or_pool.fetch(sql, recruiter_id)
    items = []
    for r in rows:
        item = dict(r)
        item["status"] = "Resolved" if item.get("resolved") else "Open"
        items.append(item)
    return items


async def update_recruiter_preferences(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool,
    recruiter_id: int,
    preferences: dict[str, Any],
) -> dict[str, Any] | None:
    """Update preference filters for an existing recruiter.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.
        preferences (dict[str, Any]): Updated preference filters dictionary.

    Returns:
        dict[str, Any] | None: Updated recruiter record or None.
    """
    pref_json = json.dumps(preferences)
    sql = """
    UPDATE recruiters
    SET preference_filters = $2::jsonb
    WHERE id = $1
    RETURNING id, name, email, preferred_channel, telegram_handle, preference_filters, created_at;
    """
    row = await conn_or_pool.fetchrow(sql, recruiter_id, pref_json)
    if row:
        res = dict(row)
        if isinstance(res.get("preference_filters"), str):
            res["preference_filters"] = json.loads(res["preference_filters"])
        return res
    return None


async def add_commit_log(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, commit_data: dict[str, Any]
) -> dict[str, Any]:
    """Insert a commit entry into the commit_logs table.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        commit_data (dict[str, Any]): Commit attributes.

    Returns:
        dict[str, Any]: Created commit log record.
    """
    sql = """
    INSERT INTO commit_logs (project_id, commit_hash, commit_message, author_name, classification)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING id, project_id, commit_hash, commit_message, author_name, commit_date, classification, created_at;
    """
    row = await conn_or_pool.fetchrow(
        sql,
        commit_data["project_id"],
        commit_data.get("commit_hash"),
        commit_data["commit_message"],
        commit_data.get("author_name", "Developer"),
        commit_data.get("classification", "Minor"),
    )
    return dict(row) if row else {}


async def get_project_commit_logs(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int, limit: int = 50
) -> list[dict[str, Any]]:
    """Retrieve commit history entries for a project.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.
        limit (int): Max commits to return. Defaults to 50.

    Returns:
        list[dict[str, Any]]: List of commit records.
    """
    sql = """
    SELECT id, project_id, commit_hash, commit_message, author_name, commit_date, classification, created_at
    FROM commit_logs
    WHERE project_id = $1
    ORDER BY commit_date DESC, id DESC
    LIMIT $2;
    """
    rows = await conn_or_pool.fetch(sql, project_id, limit)
    return [dict(r) for r in rows]


async def add_peer_suggestion(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, peer_data: dict[str, Any]
) -> dict[str, Any]:
    """Insert a peer community suggestion for a project.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        peer_data (dict[str, Any]): Peer feedback attributes.

    Returns:
        dict[str, Any]: Created peer suggestion record.
    """
    sql = """
    INSERT INTO peer_suggestions (project_id, student_id, student_name, feedback_text)
    VALUES ($1, $2, $3, $4)
    RETURNING id, project_id, student_id, student_name, feedback_text, created_at;
    """
    row = await conn_or_pool.fetchrow(
        sql,
        peer_data["project_id"],
        peer_data.get("student_id"),
        peer_data.get("student_name", "Anonymous Peer"),
        peer_data["feedback_text"],
    )
    return dict(row) if row else {}


async def get_project_peer_suggestions(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> list[dict[str, Any]]:
    """Retrieve all peer community feedback for a project.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.

    Returns:
        list[dict[str, Any]]: List of peer suggestion records.
    """
    sql = """
    SELECT id, project_id, student_id, student_name, feedback_text, created_at
    FROM peer_suggestions
    WHERE project_id = $1
    ORDER BY created_at DESC, id DESC;
    """
    rows = await conn_or_pool.fetch(sql, project_id)
    return [dict(r) for r in rows]


async def add_to_cart(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_id: int, project_id: int
) -> dict[str, Any]:
    """Add a project to a recruiter's cart/wishlist.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.
        project_id (int): Project ID.

    Returns:
        dict[str, Any]: Created or existing cart item record.
    """
    sql = """
    INSERT INTO cart_items (recruiter_id, project_id)
    VALUES ($1, $2)
    ON CONFLICT (recruiter_id, project_id) DO UPDATE SET recruiter_id = EXCLUDED.recruiter_id
    RETURNING id, recruiter_id, project_id, created_at;
    """
    row = await conn_or_pool.fetchrow(sql, recruiter_id, project_id)
    return dict(row) if row else {}


async def get_cart_items(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_id: int
) -> list[dict[str, Any]]:
    """Retrieve all projects in a recruiter's cart with project & student details.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.

    Returns:
        list[dict[str, Any]]: List of cart item records with nested project objects.
    """
    sql = """
    SELECT c.id as cart_item_id, c.recruiter_id, c.project_id, c.created_at as added_at,
           p.repo_url, p.summary, p.tags, p.ai_difficulty, p.ai_authenticity, p.ai_creativity,
           p.ai_score, p.final_score, p.last_scanned_at,
           s.id as student_id, s.name as student_name, s.github_username, s.email as student_email
    FROM cart_items c
    JOIN projects p ON c.project_id = p.id
    JOIN students s ON p.student_id = s.id
    WHERE c.recruiter_id = $1
    ORDER BY c.created_at DESC;
    """
    rows = await conn_or_pool.fetch(sql, recruiter_id)
    items = []
    for r in rows:
        d = dict(r)
        tags = d.get("tags")
        if isinstance(tags, str):
            tags = json.loads(tags)
        items.append({
            "id": d["cart_item_id"],
            "recruiter_id": d["recruiter_id"],
            "project_id": d["project_id"],
            "added_at": d["added_at"],
            "project": {
                "id": d["project_id"],
                "repo_url": d["repo_url"],
                "summary": d["summary"],
                "tags": tags or [],
                "ai_difficulty": d["ai_difficulty"],
                "ai_authenticity": d["ai_authenticity"],
                "ai_creativity": d["ai_creativity"],
                "ai_score": d["ai_score"],
                "final_score": d["final_score"],
                "last_scanned_at": d["last_scanned_at"],
                "student": {
                    "id": d["student_id"],
                    "name": d["student_name"],
                    "github_username": d["github_username"],
                    "email": d["student_email"],
                },
            },
        })
    return items


async def remove_from_cart(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, recruiter_id: int, project_id: int
) -> bool:
    """Remove a project from recruiter's cart by recruiter ID and project ID.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        recruiter_id (int): Recruiter ID.
        project_id (int): Project ID.

    Returns:
        bool: True if deleted, False if item wasn't present.
    """
    sql = "DELETE FROM cart_items WHERE recruiter_id = $1 AND project_id = $2;"
    res = await conn_or_pool.execute(sql, recruiter_id, project_id)
    return "DELETE 1" in str(res)


async def remove_cart_item_by_id(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, item_id: int
) -> bool:
    """Remove a cart item by cart item ID.

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        item_id (int): Cart item ID.

    Returns:
        bool: True if deleted, False if item wasn't present.
    """
    sql = "DELETE FROM cart_items WHERE id = $1;"
    res = await conn_or_pool.execute(sql, item_id)
    return "DELETE 1" in str(res)


async def get_project_analytics(
    conn_or_pool: asyncpg.Connection | asyncpg.Pool, project_id: int
) -> dict[str, Any] | None:
    """Retrieve comprehensive Personal Analytics bundle for a project.

    Follows the Caspian Personal Analytics Tab Layout specification (§3.1-§3.8 & §14).

    Args:
        conn_or_pool (asyncpg.Connection | asyncpg.Pool): Connection or Pool object.
        project_id (int): Project ID.

    Returns:
        dict[str, Any] | None: Structured analytics bundle or None if project not found.
    """
    project = await get_project_by_id(conn_or_pool, project_id)
    if not project:
        return None

    # 1. Rating history & trend
    ratings = await get_project_ratings_history(conn_or_pool, project_id)
    final_score = project.get("final_score") or project.get("ai_score") or 0.0
    ai_score = project.get("ai_score") or 0.0
    score_change = round(final_score - ai_score, 1)

    # 2. Metric score breakdown
    metrics = [
        {
            "name": "Technical Quality",
            "score": project.get("ai_difficulty") or 0.0,
            "weight": "40%",
            "category": "difficulty",
            "description": "Architectural complexity and technical depth evaluated by AI.",
        },
        {
            "name": "Code Authenticity",
            "score": project.get("ai_authenticity") or 0.0,
            "weight": "30%",
            "category": "authenticity",
            "description": "Code originality, structure, and non-boilerplate implementation.",
        },
        {
            "name": "Project Creativity",
            "score": project.get("ai_creativity") or 0.0,
            "weight": "30%",
            "category": "creativity",
            "description": "Novelty, problem-solving ingenuity, and design flair.",
        },
    ]

    if ratings:
        avg_rating = sum(r["rating"] for r in ratings) / len(ratings)
        metrics.append({
            "name": "Community & Recruiter Score",
            "score": round(avg_rating * 10.0, 1),
            "weight": "30% (Final Score)",
            "category": "community",
            "description": f"Average score from {len(ratings)} peer & recruiter ratings.",
        })

    # 3. Evolution: commits & activity
    commits = await get_project_commit_logs(conn_or_pool, project_id, limit=30)

    # 4. Recruiter interest & category distribution
    recruiter_matches = await find_matches(conn_or_pool, project_id)
    categories_dist: dict[str, int] = {}
    for r in recruiter_matches:
        filters = r.get("preference_filters", {})
        stacks = filters.get("tech_stack", [])
        if isinstance(stacks, list):
            for tech in stacks:
                categories_dist[tech] = categories_dist.get(tech, 0) + 1
        elif isinstance(stacks, str):
            categories_dist[stacks] = categories_dist.get(stacks, 0) + 1

    # 5. Suggestions
    recruiter_suggestions = await get_project_suggestions(conn_or_pool, project_id)
    peer_suggestions = await get_project_peer_suggestions(conn_or_pool, project_id)
    unresolved_suggs = [s for s in recruiter_suggestions if not s.get("resolved")]

    # 6. AI Next Steps (max 3 actionable recommendations)
    recommendations = []
    if (project.get("ai_difficulty") or 0.0) < 80.0:
        recommendations.append({
            "title": "Enhance Technical Depth",
            "description": "Add modular unit tests, Docker containerization, or asynchronous processing pipelines to increase architectural score.",
            "impact": "High",
            "metric": "Technical Quality",
        })
    if (project.get("ai_authenticity") or 0.0) < 85.0:
        recommendations.append({
            "title": "Refine Code Documentation",
            "description": "Expand README with architecture diagrams, setup instructions, and API references to elevate authenticity score.",
            "impact": "Medium",
            "metric": "Code Authenticity",
        })
    if unresolved_suggs:
        recommendations.append({
            "title": "Resolve Recruiter Feedback",
            "description": f"You have {len(unresolved_suggs)} open recruiter suggestion(s). Pushing fixes to GitHub will automatically resolve them and notify recruiters.",
            "impact": "High",
            "metric": "Market Fit",
        })
    elif not ratings:
        recommendations.append({
            "title": "Gather Community Ratings",
            "description": "Share your project on the feed to accumulate initial peer and recruiter ratings to boost final composite score.",
            "impact": "Medium",
            "metric": "Community Score",
        })
    if len(recommendations) < 3:
        recommendations.append({
            "title": "Continuous Integration",
            "description": "Configure automated GitHub Action CI/CD workflows and add build status badges to the repository.",
            "impact": "Low",
            "metric": "Project Maturity",
        })

    # Limit to top 3 recommendations
    recommendations = recommendations[:3]

    # Extract clean project name from repo_url
    repo_url = project.get("repo_url", "")
    project_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git") if repo_url else "Portfolio Project"

    return {
        "header": {
            "project_id": project["id"],
            "project_name": project_name,
            "repo_url": repo_url,
            "status": "Active",
            "last_scanned_at": project.get("last_scanned_at"),
            "student_id": project.get("student_id"),
            "student_name": project.get("student_name"),
            "github_username": project.get("github_username"),
            "student_email": project.get("student_email"),
        },
        "score_hero": {
            "final_score": final_score,
            "ai_score": ai_score,
            "score_change": score_change,
            "confidence": "High",
            "classification": "High-Rated Project" if final_score >= 80.0 else "Active Project",
        },
        "metrics": metrics,
        "summary": {
            "text": project.get("summary") or "AI summary is being generated for this project.",
            "tags": project.get("tags") or [],
        },
        "evolution": {
            "rating_history": ratings,
            "commits": commits,
            "total_commits": len(commits),
        },
        "recruiter_interest": {
            "matched_recruiter_count": len(recruiter_matches),
            "category_distribution": categories_dist,
            "sample_matches": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "preferred_channel": m.get("preferred_channel"),
                    "preferences": m.get("preference_filters", {}),
                }
                for m in recruiter_matches[:5]
            ],
        },
        "recruiter_suggestions": recruiter_suggestions,
        "peer_suggestions": peer_suggestions,
        "ai_recommendations": recommendations,
    }
