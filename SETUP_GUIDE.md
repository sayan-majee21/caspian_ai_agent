# 🚀 TalentCaspian — Complete Setup & Deployment Guide

This guide provides step-by-step instructions for setting up, configuring, testing, and deploying **TalentCaspian** — the AI-powered portfolio evaluation and multi-channel recruiter matching platform.

---

## 📋 Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Local Environment Setup](#2-local-environment-setup)
3. [Environment Configuration (`.env`)](#3-environment-configuration-env)
4. [Database Setup & Migration](#4-database-setup--migration)
5. [Running Test Suite](#5-running-test-suite)
6. [Running Dual Services Locally](#6-running-dual-services-locally)
7. [GitHub Webhook Integration](#7-github-webhook-integration)
8. [Git Branch & Remote Management](#8-git-branch--remote-management)
9. [SDK & Production Maintenance](#9-sdk--production-maintenance)

---

## 1. Prerequisites

Ensure you have the following installed on your system:
- **Python**: `3.11` or higher (tested on Python `3.13`)
- **PostgreSQL**: `v14` or higher (local installation or Docker)
- **Git**: Installed and configured
- **Virtual Environment Tool**: Built-in `venv` module

---

## 2. Local Environment Setup

### Step 2.1: Clone the Repository
```bash
git clone https://github.com/sayan-majee21/caspian_ai_agent.git
cd caspian_ai_agent
```

### Step 2.2: Create & Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 2.3: Install Dependencies
Install all required packages from `requirements.txt`:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Environment Configuration (`.env`)

Copy `.env.example` to create your local `.env` configuration file:

```bash
# On Windows PowerShell:
Copy-Item .env.example .env

# On Linux/macOS:
cp .env.example .env
```

### Key Configuration Variables

Edit your `.env` file with your credentials:

```ini
# ==========================================
# TalentCaspian Environment Configuration
# ==========================================

# -- Application Settings --
ENVIRONMENT=development
PORT=5001

# -- Database Configuration --
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/talentcaspian

# -- Authentication & Security --
ADMIN_API_KEY=dev_admin_key_12345
GITHUB_WEBHOOK_SECRET=dev_webhook_secret_12345
GITHUB_TOKEN=your_github_personal_access_token

# -- AI Engine (Google GenAI SDK v2.18+) --
GEMINI_API_KEY=your_google_gemini_api_key

# -- Caspian Multi-Channel Network SDK --
CASPIAN_API_KEY=your_caspian_network_api_key
CASPIAN_BASE_URL=https://api.trycaspianai.com
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
CASPIAN_EMAIL_USER=your_email_address@example.com

# -- CORS & Frontend --
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=["http://localhost:5173","https://talentcaspian.vercel.app"]
```

> [!NOTE]
> For offline development and testing, missing `GEMINI_API_KEY` or `CASPIAN_API_KEY` will trigger safe deterministic fallback heuristics without crashing services.

---

## 4. Database Setup & Migration

### Step 4.1: Create PostgreSQL Database
Ensure your PostgreSQL server is running, then create the `talentcaspian` database:

```sql
CREATE DATABASE talentcaspian;
```

### Step 4.2: Automatic Schema Initialization
When the FastAPI server starts, schema DDL tables (`students`, `projects`, `recruiters`, `project_ratings`, `suggestions`, `notification_logs`, `processed_deliveries`) are automatically created via the application lifespan hook (`database/db.py`).

---

## 5. Running Test Suite

Verify that all unit, integration, and E2E multi-agent tests pass cleanly:

```bash
python -m pytest
```

Expected output:
```text
======================== 97 passed, 1 warning in 3.11s ========================
```

---

## 6. Running Dual Services Locally

TalentCaspian operates with two complementary concurrent services:

### Service A: Main API Server (FastAPI)
The primary HTTP web server handling student registrations, recruiter preferences, rating endpoints, admin controls, and GitHub webhooks.

```bash
# Start FastAPI server on port 5001
python -m uvicorn main:app --reload --port 5001
```

Access API documentation at:
- Swagger UI: `http://localhost:5001/docs`
- ReDoc: `http://localhost:5001/redoc`

### Service B: Step 6 Listener Agent Daemon (Caspian SDK)
The background daemon that connects to the Caspian Network, listens for inbound recruiter responses (ratings/suggestions), parses intent using Gemini Flash, updates project ratings in PostgreSQL, and records suggestions.

In a **separate terminal window** (with virtual environment activated):
```bash
python caspian_agent.py
```

---

## 7. GitHub Webhook Integration

To handle automated student code pushes:
1. In your GitHub repository settings, go to **Settings ➔ Webhooks ➔ Add webhook**.
2. **Payload URL**: `https://your-domain.com/api/webhook/github` (or use `ngrok http 5001` for local testing).
3. **Content type**: `application/json`
4. **Secret**: Value of `GITHUB_WEBHOOK_SECRET` in `.env` (`dev_webhook_secret_12345`).
5. **Events**: Select **Just the `push` event**.

When a student pushes code:
- Webhook signature is validated using HMAC SHA256 (`X-Hub-Signature-256`).
- Idempotency is verified using `X-GitHub-Delivery`.
- "Major" code changes trigger Gemini re-evaluation and auto-check if recruiter suggestions were resolved, firing follow-up outreach upon resolution.

---

## 8. Git Branch & Remote Management

### Step 8.1: Check Local Branch Status
```bash
git status
```

### Step 8.2: Push Branch to GitHub Remote
To push your completed feature branch to the remote repository:

```bash
git push -u origin feature/listener-agent
```

To create a Pull Request on GitHub, visit:
`https://github.com/sayan-majee21/caspian_ai_agent/pull/new/feature/listener-agent`

---

## 9. SDK & Production Maintenance

- **Google GenAI SDK**: All LLM calls use official `google-genai>=2.18.0` SDK (`from google import genai`). Zero deprecation warnings.
- **Process Isolation**: Keep `caspian_agent.py` running in a dedicated process (e.g., via Systemd, Supervisor, PM2, or Docker container) alongside FastAPI.
- **Connection Pools**: Database connections are managed via `asyncpg` pools (`init_db_pool()`, `close_db_pool()`) and automatically released during long-running API calls.
