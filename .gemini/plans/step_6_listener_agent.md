# Step 6: Caspian Listener Agent (Reply Handling) Implementation Plan

This document outlines the detailed architecture and implementation steps for **Step 6** of the TalentCaspian project, focusing on the background listener daemon that processes incoming replies from recruiters via the Caspian multi-channel gateway.

---

## 1. Listener Daemon Architecture (`caspian_agent.py` Expansion)

The listener agent must run continuously and independently of the FastAPI web server to avoid blocking the main event loop.

-   **Process Isolation:** The listener will be executed as a standalone Python script (`python caspian_agent.py`) or as a background task/daemon managed by a process manager (e.g., systemd, supervisord, or a simple detached background process during dev).
-   **Database Pool Initialization:** Because `caspian_agent.py` runs outside FastAPI's application lifecycle, its `main()` function MUST explicitly call `await init_db_pool()` on startup and `await close_db_pool()` in a `finally` block on shutdown.
-   **SDK Integration:** It will leverage the `caspian-sdk` and utilize the unified `@client.on_message` decorator (established in Step 1 — same handler instance, not a second one) to intercept incoming messages across all supported channels (Email, Telegram).
-   **Asynchronous Processing:** While the listener loop itself might be blocking depending on the SDK's implementation, the message handling logic should be asynchronous to handle concurrent replies efficiently, particularly when communicating with the database or Gemini API.

## 2. Conversation & Context Tracking

To meaningfully process a reply, the agent needs to know *who* is replying and *what* they are replying about.

-   **Sender Resolution:**
    -   Extract the sender's identifier (Email address or Telegram handle) from the incoming Caspian message payload.
    -   Query the `recruiters` table by `email` or `telegram_handle` (both columns exist on the schema per Step 3) to find a matching record.
    -   *Fallback:* If the sender is unknown, trigger an unregistered sender workflow (see Error Handling).
-   **Session Context Mapping:**
    -   We need to determine which project the recruiter is commenting on.
    -   **Approach:** Query `notification_logs` for the most recent row matching this `recruiter_id`, ordered by `sent_at DESC`, to infer the `project_id` being discussed. This table already exists in the Step 3 schema and is populated by Agent 2's dedup check (Step 5) — no new table needed.
    -   *Note:* If the Caspian SDK exposes thread/metadata support, embedding `project_id` directly in the outbound notification and reading it back from the reply is more robust than inference — use it if available, and fall back to the `notification_logs` lookup otherwise.

## 3. Reply Parsing & Action Classification

Once the context is established, the agent must understand the intent of the recruiter's message.

-   **Intent Analysis (Gemini Flash):**
    -   Use Google Gemini (preferably the fast/lightweight Flash model) to parse the natural language reply.
    -   Prompt Gemini to classify the message into one or more categories and extract relevant entities:
        -   **Category 1: Feedback / Suggestion** (e.g., "Needs unit tests", "Add Docker setup", "The UI looks broken on mobile"). -> *Extract the specific suggestion text.*
        -   **Category 2: Rating / Interest** (e.g., "This looks great, 8/10", "I'd like to interview this student"). -> *Extract the numerical rating (if any) or boolean interest flag.*
        -   **Category 3: General Inquiry / Noise** (e.g., "Out of office", "Thanks").
-   **Fallback Parsing:**
    -   Implement lightweight regex/keyword matching (e.g., looking for numbers out of 10, or words like "fix", "add", "issue") as a fallback if the Gemini API is temporarily unavailable or for very simple replies.

## 4. Database Mutation Logic

Based on the parsed intent, the agent updates the PostgreSQL database.

-   **Handling Suggestions:**
    -   If a suggestion is extracted, insert a new record into the `suggestions` table:
        -   `project_id`: (Resolved from context via `notification_logs`)
        -   `recruiter_id`: (Resolved from sender)
        -   `suggestion_text`: (Extracted by Gemini)
        -   `resolved`: `False` (Default state)
-   **Handling Ratings:**
    -   If a rating is detected, insert into `project_ratings` with `rater_type='recruiter'`, `rater_id=recruiter_id`, and the extracted `rating`. This flows through the same `update_project_score` DAO used by the public `/api/rate` endpoint (Step 3) — no separate code path needed, since `project_ratings` doesn't distinguish storage by rater type, only by the `rater_type` column.
-   **Connection Management:** Ensure the background agent uses the existing connection pool (defined in `database/db.py`) and properly releases connections after mutations.

## 5. Feedback Loop with Agent 1 & Agent 2

The listener acts as the entry point for the continuous improvement loop.

-   **Flagging for Re-evaluation:** The creation of an unresolved suggestion (`resolved=False`) inherently flags the project.
-   **Agent 1 (Code Scanner) Integration:** When the student pushes a new commit (handled by the webhook in Step 4), Agent 1 checks the `suggestions` table for the project and evaluates whether the new code addresses pending suggestions.
-   **Agent 2 (Matcher) Integration:** Once Agent 1 marks a suggestion as `resolved=True`, Agent 2 (Step 5, Section 6) notifies the recruiter who made the suggestion — this follow-up bypasses the standard notification cooldown and is logged with `notification_logs.is_followup = true`.

## 6. Error Handling & Fallback

The agent must be resilient to messy real-world communication.

-   **Unrecognized Senders:** If a message arrives from an unknown email/handle, reply gracefully (if Caspian supports bidirectional replies) stating they are not recognized, or simply log it and ignore to prevent spam.
-   **Ambiguous Replies:** If Gemini cannot confidently classify the intent, default to logging the message for manual review or storing it as a generic "comment" without triggering automated loops.
-   **Hackathon De-scoping:** If time is constrained:
    -   *Skip Gemini parsing:* Rely purely on keyword matching (e.g., if the message contains "suggest:", treat the rest as a suggestion).
    -   *Skip Context Tracking:* Assume any reply from a recruiter applies to all their assigned projects, or require recruiters to include a project ID in their reply (less ideal UX, but easier to build).

## 7. Testing Plan (`tests/test_06_listener_agent.py`)

Robust testing is required for the background daemon.

1.  **Mocking Caspian:** Use `unittest.mock` to simulate incoming payloads from the Caspian SDK without needing a live gateway.
2.  **Mocking Gemini:** Mock the Gemini API call to return predefined classification JSONs (e.g., returning a mock suggestion extraction).
3.  **Test Cases:**
    -   `test_handle_suggestion_reply`: Simulate a message like "Add a README", ensure a new row appears in the `suggestions` table with `resolved=False`.
    -   `test_handle_rating_reply`: Simulate "Great project, 9/10", ensure `project_ratings` gets a new row and `final_score` is recalculated.
    -   `test_unknown_sender`: Simulate a reply from an unregistered email/handle, ensure it handles it gracefully without crashing.
    -   `test_context_resolution`: Ensure the agent correctly links a reply to the most recently notified `project_id` for that recruiter via `notification_logs`.
    -   `test_db_connection_leak`: Ensure database connections are returned to the pool after processing a batch of mock messages.
