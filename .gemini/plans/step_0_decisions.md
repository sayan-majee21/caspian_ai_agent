# Step 0: Decisions to Lock Before Implementation

This document outlines the final, production-grade decisions established for **TalentCaspian** before any code implementation begins. It details architectural boundaries, security considerations, and the exact specifications required to ensure a smooth development process.

---

## 1. Detailed Analysis of Locked Decisions

### 1.1 Caspian Channels Selection
**Decision:** We will restrict the initial Caspian multi-channel communication to **Email** and **Telegram**.
- **Rationale:** Email provides standard, asynchronous professional communication, while Telegram offers low-latency, real-time push notifications ideal for rapid recruiter-student matching. Other channels (e.g., Slack, Discord) add unnecessary complexity for the MVP.
- **Setup Requirements:**
  - **Email:** Standard SMTP configuration or a lightweight transactional email API (e.g., SendGrid/Mailgun) compatible with Caspian.
  - **Telegram:** A dedicated Telegram Bot Token via BotFather.
- **API Key Management:** Keys will be injected securely via environment variables. The Caspian listener worker (`caspian_agent.py`) will poll only these registered channels.
- **⚠️ Verify before Step 1:** Confirm the actual import path for the installed `caspian-sdk` package (e.g., `from caspian_sdk import CommClient` vs `from caspian import CommClient`) against Caspian's official docs. This is a one-line check but it determines whether the Step 1 script runs at all — don't assume either name without checking.

### 1.2 Frontend Hosting Architecture
**Decision:** The React frontend will be deployed separately on **Vercel** rather than served as static files from the FastAPI backend in production.
- **Rationale:** Separation of concerns. Vercel provides superior global edge caching, automated CI/CD for frontend repositories, and zero-config SSL.
- **CORS Headers:** The FastAPI backend must be explicitly configured to accept requests from the Vercel production URL and `localhost` during development.
  - Allowed Origins: `["http://localhost:5173", "https://talentcaspian.vercel.app"]`
- **Security Parameters:** Security headers (e.g., CSP, X-Frame-Options) will be strictly enforced on the backend via standard middleware.

### 1.3 Kaggle Scope Decision
**Decision:** Explicit Scope Boundary — **Drop Kaggle integration for the MVP**.
- **Rationale:** Normalizing unstructured data from Kaggle notebooks is significantly more complex than analyzing GitHub repositories. Focusing purely on GitHub repos guarantees higher quality Gemini API evaluations. We map the product's "Data Science signal" directly to the presence of Jupyter Notebooks, `.py` scripts, and data pipelines within GitHub repositories instead.
- **Scope note:** The `projects` table stores GitHub repos only. Do not reference Kaggle anywhere else in the implementation docs — this was a leftover phrase in an earlier draft of Step 3 and has been removed there.

### 1.4 Score Formula Specs
**Decision:** The final scoring mechanism will utilize a two-pronged approach combining AI evaluation and Bayesian-adjusted community ratings.

**A. AI Score Formula (Weighting: 40/30/30):**
The Gemini API will evaluate code on a scale of 0-100 across three pillars — **these names must match the schema and scanner implementation exactly (see Step 3 / Step 4):**
1. **Difficulty (40%):** Complexity of the problem solved.
2. **Authenticity (30%):** Likelihood the code is original (vs. copy-pasted boilerplate).
3. **Creativity (30%):** Novelty of the approach or application.

```
ai_score = (0.4 * difficulty) + (0.3 * authenticity) + (0.3 * creativity)
```

Gemini also extracts a `tags` array (e.g. `["python", "ml", "backend"]`) in the same call — this is what Agent 2's matching engine (Step 5) matches against recruiter `preference_filters.tech_stack`. Without this field populated, the matching engine has nothing to compare against.

**B. Community Rating (Bayesian Adjustment):**
To prevent a single 5-star rating from outranking an established project with a 4.8 average over 100 votes, we use a Bayesian average:
```math
Bayesian Rating = ( (C * m) + (votes * average_rating) ) / (C + votes)
```
- **Confidence (C):** 5 (Number of reviews required for the average to pull away from the prior)
- **Prior (m):** 5.0 (The assumed average rating across the platform, on a 1-10 scale)

**⚠️ Scale correction:** `ai_score` is 0–100. The Bayesian rating above is on a 1–10 scale. These **must be normalized to the same scale before combining** — multiply the Bayesian average by 10 before applying the 0.7/0.3 weighting. See Step 3 for the corrected formula. Without this, `final_score` never exceeds ~73 and any recruiter filter like `min_score: 85` silently matches nothing.

### 1.5 Authentication & Authorization Specification
**Decision:** Lightweight but secure API key and webhook signature verification.
- **Admin API Key:** Administrative endpoints (e.g., triggering a manual scan) will be protected via a custom header: `X-Admin-API-Key`.
- **GitHub Webhooks:** Webhook payloads from GitHub will be verified using HMAC SHA256. The application will compute the hash using a stored webhook secret and compare it against the `X-Hub-Signature-256` header.
- **Webhook idempotency:** GitHub retries failed webhook deliveries. Track processed `X-GitHub-Delivery` IDs (an in-memory set is sufficient for a hackathon) and skip any delivery ID already processed, to avoid double-scanning on a retry.

---

## 2. Environment Variables & Secret Management

A strict `.env` policy is required. The following `.env.example` structure must be committed to the repository.

```env
# ==========================================
# TalentCaspian Environment Configuration
# ==========================================

# -- Application Settings --
ENVIRONMENT=development           # REQUIRED: development, staging, production
PORT=5001                         # OPTIONAL: Default 5001

# -- Database Configuration --
DATABASE_URL=postgresql://user:password@localhost:5432/talentcaspian # REQUIRED

# -- Authentication & Security --
ADMIN_API_KEY=your_secure_admin_key_here    # REQUIRED: Protects /api/admin/*
GITHUB_WEBHOOK_SECRET=your_hmac_secret      # REQUIRED: For validating X-Hub-Signature-256
GITHUB_TOKEN=your_github_pat                # REQUIRED: Raises GitHub API rate limit from 60/hr to 5000/hr

# -- AI Agents --
GEMINI_API_KEY=your_google_gemini_api_key   # REQUIRED: For code analysis and recruiter matching

# -- Caspian Multi-Channel SDK --
CASPIAN_API_KEY=your_caspian_gateway_key    # REQUIRED
CASPIAN_BASE_URL=https://api.caspian.network # OPTIONAL: Default Caspian gateway URL
TELEGRAM_BOT_TOKEN=your_telegram_bot_token  # OPTIONAL: Required if Telegram channel is active
CASPIAN_EMAIL_USER=your_caspian_email_address # OPTIONAL: Required if Email channel is active

# -- CORS & Frontend --
FRONTEND_URL=http://localhost:5173          # REQUIRED: Vercel or local frontend origin
CORS_ORIGINS=["http://localhost:5173","https://talentcaspian.vercel.app"] # OPTIONAL: JSON array of origins
```

---

## 3. Risk Analysis and Pre-Flight Checklist

### Risk Analysis
1. **Gemini API Rate Limiting & Webhook Timeouts:** Scanning massive repositories inside GitHub webhooks might hit token limits or exceed GitHub's strict 10s HTTP timeout.
   - *Mitigation:* Webhook endpoints validate HMAC and delivery ID synchronously, return HTTP 202 Accepted immediately, and enqueue scanning tasks via `FastAPI.BackgroundTasks`.
2. **Caspian Worker Process Isolation:** FastAPI backend (`main.py`) and Caspian listener (`caspian_agent.py`) run in separate processes.
   - *Mitigation:* `caspian_agent.py` runs as an independent daemon managing its own Caspian client and `asyncpg` DB pool. FastAPI instantiates a dedicated outbound `CommClient` helper for notifications.
3. **Database Connection Leaks:** Unmanaged connections in async endpoints or standalone scripts.
   - *Mitigation:* Use FastAPI `Depends(get_db_connection)` in web routes, and explicitly invoke `init_db_pool()`/`close_db_pool()` in standalone background scripts.
4. **Score scale mismatch:** Combining a 0-100 AI score with a 1-10 community score without normalizing produces a compressed, misleading `final_score`.
   - *Mitigation:* Normalize the Bayesian average to 0-100 before weighting (see Step 3).
5. **Duplicate recruiter notifications:** Re-running the notify job without checking `notification_logs` will spam recruiters.
   - *Mitigation:* Dedup check before dispatch (see Step 5).

### Pre-Flight Checklist
Before starting **Step 2 (Core Backend Setup)**, confirm the following:
- [ ] Local PostgreSQL instance is running and accessible.
- [ ] Python 3.10+ virtual environment is initialized and activated.
- [ ] `requirements.txt` contains FastAPI, asyncpg, pydantic, caspian-sdk, and google-generativeai.
- [ ] `.env` file is created locally based on `.env.example` with valid dummy/dev credentials.
- [ ] Vercel placeholder project is created and CORS URL is known (if setting up production early).
- [ ] Step 1 (Caspian handshake) has been run and verified end-to-end on both channels — do not proceed to backend work until this is confirmed working.
