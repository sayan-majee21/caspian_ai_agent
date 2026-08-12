# TalentCaspian — Detailed Implementation Plan

**Hackathon:** Caspian AI Agent Hackathon (15 days)
**Eligibility gate:** Must use `caspian-sdk`, run on ≥2 channels via a **single** `on_message` handler. Duplicate per-channel handlers disqualify you. Demo must run live — mocked demos are not judged.

---

## Step 0 — Decisions to lock before writing code

These are cheap to decide now and expensive to redo mid-build.

| Decision | Choice | Why |
|---|---|---|
| Caspian channels | **Email + Telegram** | Both free/instant to set up. Slack is a fine swap-in for one of them. Avoid WhatsApp/X/iMessage — they need paid dev sign-in + prepaid credit. |
| Frontend hosting | Deferred — separate Vercel deployment hitting the FastAPI backend over CORS | You've already decided backend-first; this avoids re-deciding CORS/static-serving later. |
| Kaggle | **Drop from scope** unless you have a concrete use for it (see note below) | It's listed as an input source in the brief doc but never used in the plan. Either define it or remove it so it doesn't create a mismatch between your pitch and your build. |
| Score formula | AI base score (0–100) + Bayesian-adjusted community rating, weight capped until N ≥ 3 community votes | Prevents one recruiter's single rating from swinging a project's rank. |
| Auth | Simple API-key header on all `/api/admin/*` routes; HMAC signature check on the GitHub webhook | These are currently open in the original plan — that's a real hole, not a nice-to-have. |

**Kaggle note:** if you want to keep it in the pitch, the natural use is scoring a student's data-science credibility (competition rank, notebook votes) as a secondary signal feeding into the `Authenticity` metric. If you don't have time for that, cut it from the doc rather than leave it unaddressed.

---

## Step 1 — Caspian handshake (de-risk the eligibility gate first)

**Goal:** Prove the one hard requirement works, end-to-end, before writing any recruiting logic.

- `pip install caspian-sdk`
- `caspian init` / `caspian login` if using any paid channel (skip this if sticking to email + Telegram)
- Minimal script:
  ```python
  from caspian_sdk import CommClient

  client = CommClient()  # reads CASPIAN_API_KEY / CASPIAN_BASE_URL
  client.connect_email(username="talentcaspian")
  client.connect_telegram(bot_token=TELEGRAM_BOT_TOKEN)

  @client.on_message
  async def handle(message):
      await message.reply(f"Echo: {message.text}")

  client.listen()
  ```
- Send yourself a real message on both channels. Confirm both route through the **same** `handle()` function — this is the "single handler" requirement, not two handlers wired to two channels.
- Keep this script (`caspian_agent.py`) — it becomes the base for Step 5's Listener Agent and Step 4's outbound notifier. Don't rebuild the Caspian wiring twice.

**Exit criteria:** you have sent and received a message on two channels through one handler, and you can screen-record it. If this doesn't work, nothing else matters for eligibility.

---

## Step 2 — Core backend setup

**Objective:** FastAPI skeleton + Postgres connection, nothing recruiting-specific yet.

- `requirements.txt`: `fastapi`, `uvicorn`, `caspian-sdk`, `asyncpg` (preferred over psycopg2 for async FastAPI), `pytest`, `python-dotenv`, `google-generativeai` (Gemini)
- `main.py`: FastAPI app init, CORS middleware configured for your eventual Vercel frontend origin
- `database/db.py`: asyncpg connection pool, startup/shutdown hooks
- `GET /` → health check (`{"status": "ok"}`) — this is also your Caspian-independent liveness check for judges
- `.env.example` committed (never commit real keys) — `DATABASE_URL`, `GEMINI_API_KEY`, `CASPIAN_API_KEY`, `GITHUB_WEBHOOK_SECRET`

---

## Step 3 — Database schema + dashboard/admin APIs

**Objective:** Define tables and CRUD-level endpoints. No AI logic yet — that's Step 4.

### Schema

```sql
CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    github_username TEXT UNIQUE NOT NULL,
    email TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    repo_url TEXT NOT NULL,
    summary TEXT,                     -- Agent 1's write-up
    ai_difficulty NUMERIC,
    ai_authenticity NUMERIC,
    ai_creativity NUMERIC,
    ai_score NUMERIC,                 -- combined AI score
    final_score NUMERIC,              -- AI + community blended
    last_scanned_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE recruiters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    preference_filters JSONB,         -- e.g. {"domains": ["ml","backend"], "min_score": 70}
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE project_ratings (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    rater_type TEXT CHECK (rater_type IN ('recruiter','public')),
    rater_id INTEGER,                 -- nullable for public/anonymous
    rating NUMERIC CHECK (rating BETWEEN 1 AND 10),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE suggestions (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    recruiter_id INTEGER REFERENCES recruiters(id),
    suggestion_text TEXT,
    resolved BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);
```

### Endpoints

| Route | Method | Purpose | Auth |
|---|---|---|---|
| `/api/register` | POST | Onboard a student + their first repo (missing from original plan — this is what triggers Agent 1's first scan) | None (public signup) |
| `/api/dashboard` | GET | Full student/project portfolio, publicly viewable | None |
| `/api/recruiter/register` | POST | Recruiter signup with preference filters | None |
| `/api/recruiter/{id}` | GET | Recruiter details | None |
| `/api/rate` | POST | Submit a rating for a project | Rate-limited by IP or session to reduce brigading |
| `/api/suggest` | POST | Recruiter posts a suggestion on a project | API key (recruiter session) |
| `/api/admin/scan` | POST | Manually trigger Agent 1 scan on a repo | API key |
| `/api/admin/notify` | POST | Trigger Agent 2 matching + outreach | API key |

**Score formula (implement now, not later):**
```
final_score = ai_score * 0.7 + bayesian_community_avg * 0.3
bayesian_community_avg = (C * m + sum(ratings)) / (C + n)
# C = confidence constant (e.g. 5), m = prior mean (e.g. 5.0), n = number of ratings
```
This stops a single low/high rating from swinging a project's rank before it has enough votes.

---

## Step 4 — Agent 1: GitHub scanning + Gemini rating

**Objective:** Analyze repos on registration and on every push, decide if the change matters, and keep scores current.

- **Initial scan** (triggered by `/api/register` or `/api/admin/scan`):
  - Pull repo metadata + file tree via GitHub REST API (`GET /repos/{owner}/{repo}`, `GET /repos/{owner}/{repo}/contents`)
  - Send relevant content (README, main source files — cap total tokens sent) to Gemini Flash with a **fixed rubric prompt**, requesting structured JSON:
    ```json
    {
      "difficulty": 0-100,
      "authenticity": 0-100,
      "creativity": 0-100,
      "summary": "2-3 sentence write-up"
    }
    ```
  - Use the same rubric text every single call — do not let Gemini free-write scoring criteria per repo, or scores become incomparable across projects.
  - Store in `projects` table, compute `ai_score` as a weighted average of the three (define your own weights, e.g. 40/30/30).

- **GitHub webhook** (`POST /api/webhook/github`):
  - Verify `X-Hub-Signature-256` against `GITHUB_WEBHOOK_SECRET` (HMAC-SHA256) — **do not skip this**, it's a public endpoint on a public repo
  - Parse `push` event payload: commit messages + list of modified files (fetch diffs via API if needed, but keep token usage in mind)
  - Send commit summary to Gemini with a classifier prompt: "Is this a Major change (new feature, refactor, bug fix affecting functionality) or Minor (typo, formatting, docs-only)? Respond with one word."
  - **Minor** → log and stop, no DB write
  - **Major** → re-run the scoring prompt, update `projects` row, then check `suggestions` table for unresolved entries on this `project_id` — if any exist, queue a follow-up notification (handled by Agent 2/Caspian in Step 5)

---

## Step 5 — Agent 2: matching + Caspian outreach

**Objective:** Find recruiters whose filters match high-scoring projects, generate personalized messages, send via the Step 1 Caspian client.

- `/api/admin/notify` (auth-gated, can also run on a schedule via a cron-like loop):
  1. Query `projects` where `final_score` crosses recruiters' `min_score` filter and other JSONB filter fields match
  2. For each match, generate a short personalized message via Gemini: student name, project summary, why it matches the recruiter's stated interest, and a dashboard link
  3. Send via the **same Caspian client/handler** from Step 1 — reuse the connection, don't spin up a second one
  4. Keep the outbound message short — the brief itself calls out the message to recruiters should read like a notification, not an essay

- Also handle the **follow-up path** from Step 4: when a `Major` change resolves an existing `suggestion`, send a targeted follow-up to that specific recruiter rather than a generic broadcast.

---

## Step 6 — Caspian Listener Agent (reply handling)

**Objective:** Capture recruiter replies and route them back into the suggestions loop.

- `caspian_agent.py` as a standalone daemon (built on the same client from Step 1)
- On incoming message from a known recruiter (match by email/Telegram handle to `recruiters` table):
  - Parse reply text (simple keyword parsing is fine for a hackathon; full NLU is unnecessary scope)
  - Insert into `suggestions` with `project_id` inferred from conversation context (store this context — e.g., last project mentioned to that recruiter — in a lightweight in-memory or Redis-backed session map keyed by recruiter ID)
  - If the reply reads as a concrete ask (e.g., "needs tests," "add a demo video"), mark `resolved = false` so it surfaces to the student and re-triggers Agent 1's follow-up check on the next major commit

**This is the first thing to cut if you're short on time.** A working scan → score → notify loop already satisfies eligibility and demonstrates the creative use case. The reply loop is polish on top of that.

---

## Step 7 — Frontend (deferred, Vercel/Cursor)

**Objective:** Build once backend contracts are stable, so you're not chasing a moving API from the frontend side.

- Vite + React, Tailwind, Lucide icons, Recharts for score visualizations
- Student Dashboard: full portfolio, per-project score breakdown, community rating widget hitting `/api/rate`
- Recruiter pages: registration form (`/api/recruiter/register`), recruiter view of matched projects + suggestion box (`/api/suggest`)
- Deploy independently on Vercel; point `fetch` calls at your FastAPI backend's public URL; confirm CORS is open for the Vercel domain specifically (not `*` in production, for basic hygiene)

---

## Priority order if the 15 days get tight

1. Step 1 (Caspian handshake) — non-negotiable, this is eligibility itself
2. Step 2 + 3 (backend skeleton + schema) — everything depends on this
3. Step 4 (Agent 1 scanning) — this is your "creative use case" substance
4. Step 5 (Agent 2 outreach) — completes the actual demo loop
5. Step 7 (frontend) — needed for a presentable demo, but a Postman/curl walkthrough of the API + Caspian messages arriving live can carry a demo in a pinch
6. Step 6 (Listener Agent) — cut first if time runs out

---

## Open items you still need to decide

- Exact Gemini prompt/rubric text for scoring (write this once, test on 3–4 real repos, freeze it)
- Whether Kaggle stays in scope, and if so, what signal it feeds
- Rate-limiting strategy for `/api/rate` (IP-based is enough for a hackathon)
- Whether recruiter identity on Telegram/email is verified at all, or just trusted by whatever address messages you
