# Implementation Plan: Step 5 — Agent 2: Matching & Caspian Outreach

## 1. Agent 2 Architecture & Responsibilities

Agent 2 serves as the outbound communication layer of TalentCaspian, matching high-quality, pre-evaluated student projects with interested recruiters and facilitating personalized outreach.

**Key Responsibilities:**
- **Matching Engine:** Identify optimal intersections between project characteristics (`tags`, `final_score`) and recruiter preference filters (JSONB).
- **Outreach Generation:** Utilize the Gemini API to craft brief, tailored, and compelling notification messages.
- **Dispatching:** Interface with the Caspian multi-channel client to deliver these messages to recruiters via their `preferred_channel`.
- **Deduplication:** Never notify the same recruiter about the same project twice within a cooldown window.
- **Follow-Up:** Monitor for critical project updates and notify recruiters when their specific suggestions are addressed.

---

## 2. Matching Engine (`services/matching_engine.py`)

The Matching Engine leverages PostgreSQL's JSONB capabilities to efficiently query and match projects to recruiters.

**Implementation Details:**
- **Database Querying:**
  - The `recruiters` table contains a `preference_filters` JSONB column (e.g., `{"tech_stack": ["python","react"], "min_score": 70}`). Keep `min_score` values in the 0-100 range — this must match the `final_score` scale corrected in Step 3.
  - The `projects` table contains a `tags` JSONB array (populated by Agent 1 in Step 4) — this is what `tech_stack` is matched against.
  - Use `jsonb_array_elements_text(projects.tags)` and `jsonb_array_elements_text(recruiter.preference_filters->'tech_stack')` in SQL to check for tag overlap cleanly without JSONB type casting errors.
- **Filtering Logic:**
  - `final_score >= min_score`: Projects must meet or exceed the recruiter's minimum quality threshold.
  - Tag Overlap: Ensure at least one overlapping tag between the project's `tags` and the recruiter's `preference_filters.tech_stack`.
- **Service Layer:**
  - Create a `find_matches(pool, project_id: int) -> list[Recruiter]` function that calls `get_project_matches(pool, project_id)` (Step 3 DAO) to query matching recruiters.
  - Create the inverse `find_candidate_projects(pool, recruiter_id: int) -> list[Project]` calling `get_recruiter_matches(pool, recruiter_id)` (Step 3 DAO) for the `/api/recruiter/{id}` read path.

---

## 3. Personalized Outreach Generator (`services/outreach_service.py`)

This service uses the Gemini API to generate tailored messages for recruiters, highlighting why a project is relevant to them.

**Implementation Details:**
- **Prompt Engineering:**
  - **Goal:** Generate concise, professional, recruiter-friendly messages (avoiding verbose essays) — per the hackathon brief, the recruiter-facing message should read like a notification, not an essay.
  - **Context Injection:** The prompt must include:
    - Student Name
    - Repository URL
    - Brief Project Summary (`projects.summary`)
    - Matching Tags (why it fits the recruiter's `tech_stack` filter)
    - Link to the TalentCaspian Student Dashboard.
- **Functionality:**
  - Create a function `generate_outreach_message(recruiter, project) -> str` that constructs the prompt and calls the Gemini API to retrieve the drafted message.

---

## 4. Caspian Integration (`services/caspian_outreach.py`)

This service handles the actual transmission of generated messages using the Caspian SDK from the FastAPI application.

**Implementation Details:**
- **Process Isolation & Client Setup:**
  - `caspian_agent.py` runs in a separate process as an inbound listener daemon.
  - `services/caspian_outreach.py` in FastAPI (Process A) initializes a dedicated outbound `CommClient` instance (or calls Caspian REST API endpoints) so HTTP web requests do not depend on process B's memory space.
- **Dispatch Logic:**
  - Create a `dispatch_message(recruiter, message: str)` function.
  - Determine the delivery channel and recipient from `recruiter.preferred_channel` and `recruiter.email` (for `'email'`) or `recruiter.telegram_handle` (for `'telegram'`) — these columns were added to the `recruiters` schema in Step 3 specifically for this lookup.
  - Use `CommClient.send_message(channel=recruiter.preferred_channel, recipient=recipient, content=message)`. (Note: verify keyword arguments against installed SDK).
- **Error Handling:**
  - Ensure robust error handling for dispatch failures, logging issues without crashing the main application flow.

---

## 5. Deduplication Check (before every send)

**This step did not exist in the earlier draft and is required** — without it, re-running the notify job (manually or on a schedule) re-sends the same match to the same recruiter every time.

**Implementation Details:**
- Before calling `dispatch_message`, call `has_recent_notification(pool, recruiter_id, project_id, within_days=7)` (Step 3 DAO).
- If `True` **and** this is not a follow-up (`is_followup=False`), skip the send.
- If sent, insert a row into `notification_logs` with `channel`, `is_followup=False`, and the current timestamp.
- Follow-up messages (Section 6 below) are always allowed through regardless of the 7-day cooldown, since they represent a materially new event (a suggestion being resolved), but should still be logged with `is_followup=True` so the listener agent (Step 6) has accurate context on what was most recently sent.

---

## 6. Follow-Up Outreach Flow

This flow is triggered when Agent 1 detects a major commit that addresses an outstanding suggestion previously made by a recruiter.

**Implementation Details:**
- **Trigger:** When Agent 1 updates a suggestion's status to "Resolved" based on a new commit scan (Step 4).
- **Notification Generation:**
  - Craft a specific, direct notification template: *"Hi {Recruiter Name}, Student {Student Name} has updated '{Project Name}' addressing your feedback regarding {Suggestion Summary}!"*
- **Dispatch:**
  - Route this follow-up message through `caspian_outreach.py` to the specific recruiter who originated the suggestion, bypassing the 7-day cooldown as described in Section 5, and logging `notification_logs.is_followup = true`.

---

## 7. Endpoint Integration (`POST /api/admin/notify`)

An administrative endpoint to manually trigger or manage the matching and notification process.

**Implementation Details:**
- **Endpoint Definition:** Update the stub in `main.py` for `POST /api/admin/notify`.
- **Security:**
  - Implement a dependency to check the `X-Admin-API-Key` header against a configured environment variable to ensure only admins can trigger this endpoint.
- **Request Body Schema:** `{ project_id: int, recruiter_id: Optional[int] = None }` (matches Step 3). If `recruiter_id` is provided, dispatches to that single recruiter; if `None`/omitted, executes a bulk match scan across all recruiters for the project.
- **Background Execution:**
  - Utilize FastAPI's `BackgroundTasks` to execute the matching, generation, deduplication check, and dispatch logic asynchronously, ensuring the HTTP response returns immediately (e.g., `{"status": "Notification process started"}`).

---

## 8. Testing Plan (`tests/test_05_agent2_outreach.py`)

Comprehensive testing to ensure the matching logic and outreach generation function correctly without spamming real endpoints.

**Test Cases:**
1. **Matching Engine:**
   - Mock a database with specific recruiter JSONB preferences and project `tags`/scores.
   - Assert that `find_matches` correctly identifies matching recruiters (both `min_score` and tag overlap) and excludes non-matching ones.
2. **Outreach Generation:**
   - Mock the Gemini API call.
   - Assert that `generate_outreach_message` constructs the correct prompt with injected context and returns a string.
3. **Caspian Dispatch:**
   - Mock the `CommClient.send_message` method.
   - Assert that `dispatch_message` calls the client with the correct recipient (email or `telegram_handle`), channel, and content based on `recruiter.preferred_channel`.
4. **Deduplication:**
   - Seed a `notification_logs` row for a recruiter/project pair sent 2 days ago.
   - Assert a second `/api/admin/notify` run for the same pair does **not** dispatch a message.
   - Assert a follow-up (`is_followup=True`) for the same pair **does** dispatch, bypassing the cooldown.
5. **Follow-Up Logic:**
   - Test the flow where a resolved suggestion correctly triggers a mocked notification to the originating recruiter.
6. **Endpoint Authorization & Background Execution:**
   - Test `POST /api/admin/notify` with and without a valid API key.
   - Verify that the background task is queued upon a successful request.
