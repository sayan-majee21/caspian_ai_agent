# 🪟 TalentCaspian — Windows Local Live Setup Guide (Real GitHub & Real Telegram)

This guide provides exact **Windows (PowerShell & CMD)** step-by-step instructions to set up, configure, and run **TalentCaspian** locally on your machine connected to **real live external services**:
- 🐙 **Real GitHub Repositories**: Fetching real trees, source code, and READMEs via GitHub REST API with a personal access token.
- 🧠 **Real Gemini AI Evaluations**: Generating real portfolio scores, tags, and summaries using Gemini Flash (`gemini-1.5-flash`).
- ✈️ **Real Telegram Messages**: Delivering live recruiter notifications and follow-up alerts directly to your Telegram phone app.
- 🔄 **Real Recruiter Feedback Loop**: Replying from your phone via Telegram to update project ratings and track suggestions.

---

## 🔑 Step 1: Obtain Your Real API Keys & Tokens

### 1.1 Google Gemini API Key
1. Open your browser and go to [Google AI Studio](https://aistudio.google.com/).
2. Click **Create API Key**.
3. Copy your API key.

### 1.2 GitHub Personal Access Token (PAT)
1. Go to [GitHub Developer Settings ➔ Personal Access Tokens (Classic)](https://github.com/settings/tokens).
2. Click **Generate new token (classic)**.
3. Name it `TalentCaspian-Local-Windows`.
4. Select scope: `repo` (for private repositories) or leave default for public repositories.
5. Copy your token.

### 1.3 Telegram Bot Token & Username
1. Open the Telegram app on your phone or PC and search for `@BotFather`.
2. Send `/newbot`, enter a display name (e.g. `MyTalentCaspianBot`) and username (e.g. `my_talentcaspian_bot`).
3. Copy the HTTP API Bot Token provided by BotFather.
4. Search for your newly created bot on Telegram, click **Start**, and send it a test message (e.g., `"Hello"`).

### 1.4 Caspian Network Key
1. Obtain your Caspian API key from your Caspian provider or network dashboard.

---

## ⚙️ Step 2: Configure Your Personal `.env` File on Windows

Open **Windows PowerShell** in `D:\mobile` and create your `.env` file from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Now open `D:\mobile\.env` in VS Code or Notepad, and insert your real credentials:

```ini
# ==========================================
# TalentCaspian Windows Live Configuration
# ==========================================

ENVIRONMENT=development
PORT=5001

# Windows PostgreSQL Connection
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/talentcaspian

# Security Keys
ADMIN_API_KEY=your_admin_api_key
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret

# Real GitHub Personal Access Token
GITHUB_TOKEN=your_github_personal_access_token

# Real Google Gemini API Key
GEMINI_API_KEY=your_google_gemini_api_key

# Real Caspian & Telegram Credentials
CASPIAN_API_KEY=your_caspian_api_key
CASPIAN_BASE_URL=https://api.trycaspianai.com
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
CASPIAN_EMAIL_USER=your_email@example.com

# Frontend URL
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=["http://localhost:5173"]
```

---

## 🗄️ Step 3: Initialize PostgreSQL Database on Windows

1. Ensure the PostgreSQL service is running on Windows (Check via `Services.msc` or pgAdmin 4).
2. Open **SQL Shell (psql)** or **PowerShell** and create the database:

```powershell
# Using psql in PowerShell (or run in pgAdmin Query Tool)
psql -U postgres -c "CREATE DATABASE talentcaspian;"
```

> [!NOTE]
> Database tables (`students`, `projects`, `recruiters`, `project_ratings`, `suggestions`, `notification_logs`, `processed_deliveries`) are automatically created when you start the FastAPI server!

---

## 🚀 Step 4: Launch Dual Local Services in Windows PowerShell

Open **two separate Windows PowerShell windows** inside `D:\mobile`.

### Terminal 1: Launch FastAPI API Server
```powershell
# Activate venv & run FastAPI
.\venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 5001
```
*Expected log:* `INFO: Application startup complete. Database pool initialized.`

### Terminal 2: Launch Caspian Telegram Listener Daemon
```powershell
# Activate venv & run Caspian Daemon
.\venv\Scripts\Activate.ps1
python caspian_agent.py
```
*Expected log:* `INFO: Caspian Listener Agent daemon starting... Listening for inbound messages.`

---

## 🧪 Step 5: Test Live E2E Flow Using Windows PowerShell

### 5.1 Register a Real Student & Public GitHub Repo
Run this PowerShell script to register a real student with a live GitHub repository:

```powershell
$body = @{
    name = "Sayan Majee"
    email = "sayan@example.com"
    github_username = "sayan-majee21"
    repo_url = "https://github.com/sayan-majee21/caspian_ai_agent"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5001/api/register" -Method Post -ContentType "application/json" -Body $body
```
> ⚙️ **What happens**: FastAPI calls GitHub API to fetch real repo files, sends code to Gemini Flash API, calculates real AI quality scores, and stores the project in PostgreSQL.

---

### 5.2 Register Yourself as a Recruiter with Telegram
Register your recruiter profile with your real Telegram handle:

```powershell
$body = @{
    name = "Senior Tech Recruiter"
    email = "recruiter@example.com"
    preferred_channel = "telegram"
    telegram_handle = "@YourTelegramUsername"
    preference_filters = @{
        min_score = 60
        tech_stack = @("python", "fastapi", "postgresql")
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:5001/api/recruiter/register" -Method Post -ContentType "application/json" -Body $body
```

---

### 5.3 Trigger Real Outbound Telegram Notification
Trigger the recruiter outreach evaluation via Admin API:

```powershell
Invoke-RestMethod -Uri "http://localhost:5001/api/admin/notify" `
  -Method Post `
  -Headers @{ "X-Admin-API-Key" = "your_admin_api_key" }
```

> 📱 **Check your Telegram app on your phone!**  
> You will receive a live personalized message generated by Gemini Flash detailing the student's project, matching tech stack, and portfolio dashboard link.

---

### 5.4 Send a Live Reply from Telegram
Open the message on Telegram on your phone and reply directly:

> `"Rating: 9/10. Great architecture! I suggest adding Docker container setup for automated deployment."`

> ⚙️ **What happens**: 
> 1. `caspian_agent.py` in Terminal 2 captures your reply from Telegram.
> 2. `parse_recruiter_reply` extracts intent `suggestion`, rating `9`, and suggestion text `"adding Docker container setup for automated deployment"`.
> 3. Recalculates `final_score` in PostgreSQL and records the unresolved suggestion.

---

### 5.5 Test Real GitHub Code Push & Auto Resolution via ngrok on Windows

1. Download [ngrok for Windows](https://ngrok.com/download) or install via `winget install ngrok`.
2. Open a third PowerShell window and expose port 5001:
   ```powershell
   ngrok http 5001
   ```
3. Copy your ngrok HTTPS forwarding URL (e.g., `https://abc1234.ngrok-free.app`).
4. Go to your GitHub repo ➔ **Settings ➔ Webhooks ➔ Add webhook**:
   - **Payload URL**: `https://abc1234.ngrok-free.app/api/webhook/github`
   - **Content type**: `application/json`
   - **Secret**: `your_github_webhook_secret`
   - **Events**: `Just the push event`
5. Push a commit to your repo with commit message: `"feat: add Dockerfile and docker-compose deployment setup"`.

> 📲 **Instant Follow-up Telegram Alert!**  
> Gemini checks the push, confirms the suggestion was resolved, and automatically sends a live follow-up notification straight to your Telegram phone app!

---

## 🎯 Windows Verification Checklist

- [x] `.env` populated in `D:\mobile\.env`.
- [x] Windows PowerShell virtual environment activated (`.\venv\Scripts\Activate.ps1`).
- [x] FastAPI server running on port 5001 (`python -m uvicorn main:app --reload --port 5001`).
- [x] Caspian daemon running in second PowerShell window (`python caspian_agent.py`).
- [x] Real Telegram notification received on phone.
- [x] Live reply from phone parsed and stored in PostgreSQL.
