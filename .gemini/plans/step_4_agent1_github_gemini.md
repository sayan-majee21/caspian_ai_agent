# TalentCaspian: Step 4 — Agent 1 (GitHub Scanning + Gemini Rating) Implementation Plan

## 1. Agent 1 Architecture & Responsibilities
Agent 1 serves as the primary evaluation engine for student submissions. Its core responsibilities include:
*   **Deep Inspection:** Analyzing GitHub repositories immediately upon student registration and tracking subsequent changes via push webhooks.
*   **Quality Evaluation:** Utilizing the Google Gemini Flash API to perform automated, consistent code quality assessments based on predefined metrics.
*   **Database Synchronization:** Ensuring the `projects` table remains up-to-date with the latest scores, tags, and summaries derived from repo activity.

## 2. Initial Repo Scanner (`services/github_service.py` & `services/gemini_scanner.py`)

### GitHub API Integration
*   **Tooling:** Use `httpx` for asynchronous, non-blocking calls to the GitHub API, authenticated with `GITHUB_TOKEN` (raises rate limit from 60/hr to 5000/hr).
*   **Data Extraction:**
    *   Fetch basic repository details (stars, forks, language).
    *   Retrieve the `README.md` content.
    *   Fetch the file tree to identify key structural components.
    *   Download the contents of key source code files (e.g., `*.py`, `*.js`, `*.tsx`, `*.java`, `*.cpp`).
*   **Limits:** Implement strict size and token caps per file (e.g., limit file size to 50KB or truncate to the first ~3,000 tokens) to avoid exceeding Gemini context limits and reduce processing time.

### Gemini Flash Integration
*   **Fixed System Prompt:** Configure the Gemini Flash API with a strict system prompt instructing it to act as a senior technical recruiter evaluating a student's portfolio project. **Use the identical rubric text on every call** (initial scan and re-evaluation) — this is what keeps scores comparable across projects and across time.
*   **Rubric & Metrics:** The model must evaluate the code and output specific fields — **these field names are fixed and must match the `projects` schema exactly (Step 3):**
    *   `difficulty` (0-100): Complexity of the problem solved. → stored as `ai_difficulty`
    *   `authenticity` (0-100): Likelihood the code is original (vs. copy-pasted boilerplate). → stored as `ai_authenticity`
    *   `creativity` (0-100): Novelty of the approach or application. → stored as `ai_creativity`
    *   `tags` (array of strings, e.g. `["python", "ml", "backend"]`): Domain/tech-stack signals used later by Agent 2's matching engine (Step 5). **This field did not exist in earlier drafts — it is required, or Agent 2 has nothing to match recruiter `tech_stack` filters against.**
    *   `summary`: A concise 2-3 sentence overview of the project's purpose and technical merit. → stored as `summary`
*   **Schema Enforcement:** Enforce the response format by setting `response_mime_type="application/json"` and providing a JSON schema definition to the Gemini API (Structured Outputs), covering all five fields above.
*   **Score Calculation:** Compute an aggregated `ai_score` using a weighted formula:
    `ai_score = (0.4 * difficulty) + (0.3 * authenticity) + (0.3 * creativity)`

## 3. GitHub Webhook Handler (`POST /api/webhook/github`)

### Security and Verification
*   **HMAC Verification:** Validate all incoming webhooks using the `X-Hub-Signature-256` header against a locally stored webhook secret to ensure authenticity. Reject with 401 on mismatch.
*   **Delivery Idempotency:** GitHub retries webhook deliveries that fail or time out. Extract the `X-GitHub-Delivery` header (a UUID unique per delivery attempt — retries of the *same* event reuse it) and check against a processed-deliveries store before doing any work. For single-worker testing, an in-memory `set()` is sufficient; for multi-worker Uvicorn setups, use a lightweight `processed_deliveries` database table (`delivery_id VARCHAR(255) PRIMARY KEY`) to prevent workers from bypassing idempotency. Skip processing (return 200/202 immediately) if the ID has already been seen.

### Event Processing & Asynchronous Execution
*   **Event Filtering:** Only process `push` events; ignore others to conserve resources.
*   **Preventing Timeout Failures:** GitHub webhooks time out if an HTTP response is not returned within 10 seconds. To prevent timeouts caused by network file fetching and Gemini LLM calls:
    1. Synchronously verify HMAC signature and check `X-GitHub-Delivery` idempotency.
    2. Return `HTTP 202 Accepted` immediately.
    3. Enqueue the commit diff analysis and Gemini evaluation logic via `FastAPI.BackgroundTasks`.
*   **Background Task DB Pool Access:** Note that `BackgroundTasks` execute outside the HTTP request/response lifecycle and do not use FastAPI request-scoped `Depends(get_db_connection)` generators. The background task function must acquire connection pools directly via `database.db.is_pool_ready()` and `database.db.DB_POOL.acquire()`.
*   **Diff Analysis:** Extract the commit diffs or list of modified files from the webhook payload in the background task.

### Gemini Classifier: Major vs. Minor Updates
*   Before triggering a full re-evaluation, use a smaller, faster Gemini prompt to classify the push:
    *   **Prompt context:** "Given these commit messages and modified file paths, is this a 'Major' functional update or a 'Minor' update (typos, readme tweaks, formatting)?"
    *   **Minor Update:** Log the event and ignore. No database write.
    *   **Major Update:** Trigger the full re-evaluation flow.

### Post-Evaluation Workflow (Major Pushes)
*   **Update Database:** Overwrite `ai_difficulty`, `ai_authenticity`, `ai_creativity`, `ai_score`, `tags`, and `summary` on the `projects` table via `update_project_ai_scores` (Step 3 DAO).
*   **Recompute `final_score`:** `update_project_ai_scores` must call `update_project_score` in the same operation — `final_score` depends on `ai_score` and goes stale otherwise if no one submits a new community rating. Do not update `ai_score` without also refreshing `final_score`.
*   **Check Suggestions:** Query the `suggestions` table for any unresolved entries linked to this `project_id` (e.g., a recruiter asked them to "add unit tests"). Determine if the new push addresses the suggestion (a targeted Gemini prompt comparing the suggestion text to the diff works for a hackathon) and, if resolved, set `resolved = true` and trigger follow-up outreach via Agent 2 (Step 5).

## 4. Database Integration & Rate Limiting

### Database Operations
*   Perform all database updates asynchronously to avoid blocking the main FastAPI event loop.
*   Update the exact columns defined in the Step 3 schema: `ai_difficulty`, `ai_authenticity`, `ai_creativity`, `ai_score`, `final_score`, `tags`, `summary`, `last_scanned_at`. (There is no `metrics_json` column — do not write to a field that doesn't exist in the schema.)

### Rate Limiting & Quota Management
*   **GitHub API:** Utilize the `GITHUB_TOKEN` environment variable for authenticated requests to significantly increase rate limits (from 60/hr to 5000/hr). Implement standard retry logic with exponential backoff for `403 Rate Limit Exceeded` errors.
*   **Gemini API:** Implement a queuing mechanism or rudimentary rate limiter (e.g., `asyncio.Semaphore`) to respect Gemini Flash TPM/RPM limits, especially during bulk registrations.

## 5. Testing Plan (`tests/test_04_agent1_scanner.py`)

*   **Mocking GitHub API:** Use `respx` or `pytest-httpx` to mock responses from `api.github.com` (repo details, file contents) to prevent rate limiting during tests.
*   **Mocking Gemini API:** Mock the Google GenAI client to return a deterministic JSON payload representing `difficulty`, `authenticity`, `creativity`, `tags`, and `summary`.
*   **Testing Evaluation Logic:** Ensure the `ai_score` calculation correctly weights the mocked metrics, and that `tags` and `summary` are persisted alongside it.
*   **Testing `final_score` Refresh:** After a mocked major-push re-evaluation, assert `final_score` in the database has been recomputed (not just `ai_score`).
*   **Testing Webhook HMAC:** Write a test that sends a valid signed payload and asserts HTTP 200, and another test with an invalid signature that asserts HTTP 401.
*   **Testing Webhook Idempotency:** Send the same `X-GitHub-Delivery` ID twice; assert the second delivery is a no-op (no second Gemini call, no duplicate DB write).
*   **Testing Classifier:** Mock the minor vs. major classification step to ensure minor updates don't trigger a full evaluation flow.
