# TalentCaspian Implementation Plan: Step 3 — Database Schema & Dashboard/Admin APIs

## Overview
This document outlines the detailed implementation plan for **Step 3** of the TalentCaspian project. It covers the creation of the relational database schema, the implementation of core API endpoints for students, recruiters, and administrators, and the specific scoring calculations used to evaluate projects.

## 1. Relational Database Schema (`database/db.py`)
We will use PostgreSQL for our database. The following SQL statements represent the core table structures required for TalentCaspian.

### 1.1 Table Definitions

**`students`**
Stores information about the students participating in the platform.
```sql
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    github_username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**`projects`**
Stores the portfolio projects (GitHub repos) submitted by students.
```sql
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    repo_url TEXT UNIQUE NOT NULL,
    summary TEXT,
    tags JSONB DEFAULT '[]'::jsonb,     -- e.g. ["python","ml","backend"] — extracted by Agent 1 (Step 4)
                                          -- REQUIRED for Agent 2's matching engine (Step 5) to have anything
                                          -- to compare against recruiter preference_filters.tech_stack
    ai_difficulty FLOAT,
    ai_authenticity FLOAT,
    ai_creativity FLOAT,
    ai_score FLOAT,
    final_score FLOAT,
    last_scanned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**`recruiters`**
Stores recruiter profiles and their preferences for matching.
```sql
CREATE TABLE IF NOT EXISTS recruiters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    preferred_channel VARCHAR(50) DEFAULT 'email',  -- 'email' | 'telegram' — required by Agent 2 (Step 5)
    telegram_handle VARCHAR(255),                    -- nullable; required only if preferred_channel = 'telegram'
    preference_filters JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**`project_ratings`**
Stores ratings given to projects by users/recruiters.
```sql
CREATE TABLE IF NOT EXISTS project_ratings (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rater_type VARCHAR(50) NOT NULL, -- e.g., 'public', 'recruiter'
    rater_id INTEGER, -- Optional, NULL if public anonymous rating
    rater_ip_hash VARCHAR(64), -- sha256 of submitter IP, for rate limiting (see §3.1)
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Rate limit: one rating per project per IP per day
CREATE UNIQUE INDEX IF NOT EXISTS uq_rating_per_ip_per_day
    ON project_ratings (project_id, rater_ip_hash, (created_at::date))
    WHERE rater_ip_hash IS NOT NULL;
```

**`suggestions`**
Stores specific feedback/suggestions from recruiters on projects.
```sql
CREATE TABLE IF NOT EXISTS suggestions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    recruiter_id INTEGER NOT NULL REFERENCES recruiters(id) ON DELETE CASCADE,
    suggestion_text TEXT NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**`notification_logs`**
Tracks recruiter notification context for stateful reply handling and to prevent duplicate outreach.
```sql
CREATE TABLE IF NOT EXISTS notification_logs (
    id SERIAL PRIMARY KEY,
    recruiter_id INTEGER NOT NULL REFERENCES recruiters(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    channel VARCHAR(50),
    is_followup BOOLEAN DEFAULT FALSE, -- true if triggered by a resolved suggestion, not a fresh match
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 1.2 Indexes
To ensure high performance on common queries, we will create the following indexes:
```sql
CREATE INDEX idx_projects_student_id ON projects(student_id);
CREATE INDEX idx_projects_tags ON projects USING GIN (tags);
CREATE INDEX idx_project_ratings_project_id ON project_ratings(project_id);
CREATE INDEX idx_suggestions_project_id ON suggestions(project_id);
CREATE INDEX idx_recruiters_preference_filters ON recruiters USING GIN (preference_filters);
CREATE INDEX idx_notification_logs_recruiter_project ON notification_logs(recruiter_id, project_id, sent_at DESC);
```

## 2. Score Calculation Formula & Utility (`database/scoring.py` or `database/db.py`)
The project ranking relies on a combination of AI evaluation and human ratings. We use a Bayesian average to ensure statistical significance for human ratings.

### 2.1 Formula

**⚠️ Scale correction applied:** `ai_score` is on a 0–100 scale. Community ratings are submitted 1–10. The Bayesian average of those ratings must be rescaled to 0–100 *before* combining with `ai_score` — otherwise `final_score` compresses to roughly 0–73 and any recruiter filter expecting a 0–100 range (e.g. `min_score: 85`) will never match.

```
bayesian_avg_raw   = (C * m + sum(ratings)) / (C + n)     # still 1-10 scale
bayesian_avg_scaled = bayesian_avg_raw * 10                # normalized to 0-100

final_score = (ai_score * 0.7) + (bayesian_avg_scaled * 0.3)
```
- `C` = 5 (confidence constant, represents the weight of the prior)
- `m` = 5.0 (prior mean rating, 1-10 scale)
- `n` = total number of ratings received
- `sum(ratings)` = sum of all received ratings (1-10 scale)

### 2.2 Python Implementation
```python
def calculate_bayesian_average(ratings: list[int], C: float = 5.0, m: float = 5.0) -> float:
    """Returns a value on the same 1-10 scale as the input ratings."""
    n = len(ratings)
    sum_ratings = sum(ratings)
    return (C * m + sum_ratings) / (C + n)

def calculate_final_score(ai_score: float, ratings: list[int]) -> float:
    """ai_score: 0-100 scale. ratings: list of 1-10 community ratings.
    Returns final_score on a 0-100 scale."""
    ai_score = ai_score or 0.0
    bayesian_avg_raw = calculate_bayesian_average(ratings)
    bayesian_avg_scaled = bayesian_avg_raw * 10  # normalize 1-10 -> 0-100
    return (ai_score * 0.7) + (bayesian_avg_scaled * 0.3)
```

## 3. API Endpoints Implementation
The following FastAPI endpoints will be implemented to support the frontend and integrations.

### 3.1 Public & Student APIs
*   **`POST /api/register`**
    *   **Description:** Registers a new student and optionally their initial repository.
    *   **Payload:** `{ name, email, github_username, repo_url (optional) }`
    *   **Logic:** Inserts into `students`, if `repo_url` provided, inserts into `projects` with null scores and empty `tags`. Triggers Agent 1's initial scan (Step 4) asynchronously.

*   **`GET /api/dashboard`**
    *   **Description:** Retrieves the portfolio feed.
    *   **Query Params:** `page`, `limit`, `search_query`, `min_score`
    *   **Logic:** Returns a paginated list of projects ordered by `final_score` descending.

*   **`POST /api/rate`**
    *   **Description:** Submits a rating (1-10) for a project.
    *   **Payload:** `{ project_id, rater_type, rater_id (optional), rating }`
    *   **Logic:** Hash the submitter's IP (sha256) and store as `rater_ip_hash`. Insert into `project_ratings` — the unique index `uq_rating_per_ip_per_day` will reject a second rating from the same IP on the same project the same day (return 409 on conflict). On success, triggers asynchronous recalculation of `final_score` via `update_project_score`.

### 3.2 Recruiter APIs
*   **`POST /api/recruiter/register`**
    *   **Description:** Creates a recruiter profile.
    *   **Payload:** `{ name, email, preferred_channel, telegram_handle (required if preferred_channel='telegram'), preference_filters (JSON) }`
    *   **Logic:** Inserts into `recruiters`. Validate `telegram_handle` is present when `preferred_channel == 'telegram'`.

*   **`GET /api/recruiter/{id}`**
    *   **Description:** Retrieves a recruiter's details and a list of projects matching their `preference_filters`.
    *   **Logic:** Fetches recruiter info, then queries `projects` where `final_score >= preference_filters.min_score` AND `tags` overlaps `preference_filters.tech_stack` (JSONB containment/overlap operators).

*   **`POST /api/suggest`**
    *   **Description:** Allows recruiters to leave feedback on a project.
    *   **Payload:** `{ project_id, recruiter_id, suggestion_text }`
    *   **Logic:** Inserts into `suggestions`.

### 3.3 Admin / Background APIs (Stubs)
*   **`POST /api/admin/scan`**
    *   **Description:** Triggers the AI scanning process (Gemini integration).
    *   **Payload:** `{ project_id }` or empty for all pending.
    *   **Logic:** Currently a stub. Will eventually queue a background task for Gemini code analysis (Step 4). Includes basic auth check (`X-Admin-API-Key`).

*   **`POST /api/admin/notify`**
    *   **Description:** Triggers the recruiter notification process via Caspian SDK.
    *   **Payload:** `{ project_id: int, recruiter_id: Optional[int] = None }` (if `recruiter_id` is provided, dispatches to that single recruiter; if `None`/omitted, executes a bulk match scan across all recruiters for the given project).
    *   **Logic:** Currently a stub. Will eventually send multi-channel messages (Step 5), checking `notification_logs` first to avoid duplicate sends. Includes basic auth check.

## 4. Data Access Objects (DAOs) / Query Helpers (`database/db.py`)
To keep route functions clean, we will implement helper functions in `db.py`:
*   `async def create_student(pool, student_data)`
*   `async def create_project(pool, project_data)`
*   `async def get_projects_feed(pool, page, limit, filters)`
*   `async def add_project_rating(pool, rating_data)` -> raises a catchable conflict if `uq_rating_per_ip_per_day` triggers
*   `async def update_project_score(pool, project_id)` -> fetches ratings inside a transaction (`SELECT rating FROM project_ratings WHERE project_id = $1 FOR UPDATE` to avoid concurrent lost-update race conditions), calls `calculate_final_score`, and updates `final_score` on the `projects` row
*   `async def update_project_ai_scores(pool, project_id, ai_difficulty, ai_authenticity, ai_creativity, ai_score, tags, summary)` -> writes Agent 1's output, then calls `update_project_score` to refresh `final_score` in the same operation
*   `async def create_recruiter(pool, recruiter_data)`
*   `async def get_recruiter_matches(pool, recruiter_id)`: Gets candidate projects for a recruiter:
    ```sql
    SELECT p.* 
    FROM projects p, recruiters r
    WHERE r.id = $1
      AND p.final_score >= COALESCE((r.preference_filters->>'min_score')::float, 0)
      AND (
        r.preference_filters->'tech_stack' IS NULL 
        OR r.preference_filters->'tech_stack' = '[]'::jsonb
        OR EXISTS (
          SELECT 1 
          FROM jsonb_array_elements_text(p.tags) tag
          WHERE tag = ANY (
            SELECT jsonb_array_elements_text(r.preference_filters->'tech_stack')
          )
        )
      )
    ORDER BY p.final_score DESC;
    ```
*   `async def find_matches(pool, project_id)` / `get_project_matches(pool, project_id)`: Gets candidate recruiters matching a specific evaluated project (used by Agent 2 in Step 5):
    ```sql
    SELECT r.*
    FROM recruiters r, projects p
    WHERE p.id = $1
      AND p.final_score >= COALESCE((r.preference_filters->>'min_score')::float, 0)
      AND (
        r.preference_filters->'tech_stack' IS NULL
        OR r.preference_filters->'tech_stack' = '[]'::jsonb
        OR EXISTS (
          SELECT 1
          FROM jsonb_array_elements_text(p.tags) tag
          WHERE tag = ANY (
            SELECT jsonb_array_elements_text(r.preference_filters->'tech_stack')
          )
        )
      );
    ```
*   `async def add_suggestion(pool, suggestion_data)`
*   `async def has_recent_notification(pool, recruiter_id, project_id, within_days=7) -> bool` -> used by Step 5 to dedupe

## 5. Testing Plan (`tests/test_03_db_apis.py`)
We will use `pytest` and `pytest-asyncio` for comprehensive testing.

### 5.1 Unit Tests
*   **Scoring Logic:** Test `calculate_bayesian_average` and `calculate_final_score` with various inputs (no ratings, many ratings, high/low AI scores) to ensure mathematical correctness.
*   **Scale Assertion:** Explicitly assert `calculate_final_score(100, [10]*20)` approaches 100 (not ~73) to guard against the scale-mismatch regression.

### 5.2 Integration Tests
*   **Database Schema:** Ensure tables are created successfully on startup, including the new `tags`, `preferred_channel`, `telegram_handle`, and `rater_ip_hash` columns.
*   **Student Registration:** Test `/api/register` with valid data, duplicate emails (expect 400), and missing fields (expect 422).
*   **Dashboard Feed:** Test `/api/dashboard` pagination and sorting logic.
*   **Rating & Scoring:**
    1.  Create a project.
    2.  Hit `/api/rate` multiple times from different simulated IPs.
    3.  Verify a second rating from the same IP on the same day returns 409.
    4.  Verify the `final_score` in the database updates correctly and lands in the 0-100 range.
*   **Recruiter Flow:** Test recruiter registration (including the `telegram_handle` validation), and fetching matched projects using `tags` overlap.
*   **Admin Stubs:** Ensure `/api/admin/scan` and `/api/admin/notify` return the expected stub responses (e.g., `{"status": "queued"}`).
