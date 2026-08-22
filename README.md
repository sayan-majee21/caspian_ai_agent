<div align="center">

# ⚡ TalentCaspian
### **Autonomous Multi-Channel AI Recruiting & Live Portfolio Intelligence Agent**

*Built for the **Caspian AI Agent Hackathon 2025/2026***

[![Hackathon](https://img.shields.io/badge/Hackathon-Caspian_AI_Agent-6366F1?style=for-the-badge&logo=rocket&logoColor=white)](https://trycaspianai.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40%2B-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Google Gemini](https://img.shields.io/badge/AI_Engine-Gemini_Flash-8E75C2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![Multi-Channel](https://img.shields.io/badge/Channels-Telegram%20%7C%20Email-0088CC?style=for-the-badge&logo=telegram&logoColor=white)](https://trycaspianai.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-F59E0B?style=for-the-badge&logo=open-source-initiative&logoColor=white)](LICENSE)

<br/>

> **"Your AI agent can think. TalentCaspian gives it hands, reach, and real-time intelligence."**  
> TalentCaspian autonomously audits student codebases directly from GitHub, computes deep multi-dimensional quality metrics, and uses **Caspian** to deliver personalized candidate dossiers to technical recruiters across **Telegram and Email** with a bi-directional continuous feedback loop.

---

[Explore Features](#-key-features) • [Interactive Architecture](#-interactive-data-flow--architecture) • [Live UI Walkthrough](#-live-dashboard--ui) • [Quickstart Guide](#-quickstart--installation) • [Caspian Integration](#-caspian-multi-channel-engine) • [API Reference](#-api-endpoints)

---

</div>

<br/>

## 🎯 Executive Summary & The Problem We Solve

```
┌────────────────────────────────────────┐       ┌────────────────────────────────────────┐
│        THE BROKEN RECRUITING LOOP      │       │       THE TALENTCASPIAN REVOLUTION     │
├────────────────────────────────────────┤       ├────────────────────────────────────────┤
│ ❌ Static, exaggerated PDF resumes     │  ───> │ ✅ Real-time GitHub commit & AST audits│
│ ❌ Recruiters drown in 1000s of apps   │  ───> │ ✅ AI-matched talent filtered by stack │
│ ❌ Students get ghosted with no feedback│  ───> │ ✅ Instant Telegram recruiter feedback │
│ ❌ Portfolios go stale after submission│  ───> │ ✅ Auto-resolution on new code pushes  │
└────────────────────────────────────────┘       └────────────────────────────────────────┘
```

Technical hiring is fundamentally broken. Early-career developers are evaluated using flat resumes that fail to reflect actual software craftsmanship, problem-solving skills, or code quality. Meanwhile, recruiters spend hundreds of hours manually screening unqualified candidates while lacking the domain bandwidth to inspect live Git repositories.

**TalentCaspian** eliminates this friction with an autonomous AI agent ecosystem:
1. **Live Code Intelligence**: Evaluates repositories on **Difficulty**, **Authenticity**, and **Creativity** using Google Gemini Flash.
2. **Autonomous Caspian Multi-Channel Outreach**: Matches top projects to relevant recruiters and delivers personalized candidate briefs to their **Telegram** or **Email** inbox.
3. **Bi-Directional Feedback & Auto-Resolution**: Recruiters reply directly on Telegram with ratings or suggestions. When the student pushes a fix to GitHub, TalentCaspian receives the webhook, verifies the fix, and alerts the recruiter in real time!

---

## ⚡ Key Features

| Capability | What It Does | Technology |
| :--- | :--- | :--- |
| 🔍 **Deep Code Scanner** | Clones and inspects AST, commit histories, dependency manifests, and code complexity. | `github_service.py` + `gemini_scanner.py` |
| 🧠 **Tri-Metric AI Scoring** | Computes 0–100 quality scores based on Difficulty (40%), Authenticity (30%), & Creativity (30%). | `database/scoring.py` |
| 🌐 **Unified Caspian Agent** | Runs a single `on_message` handler servicing Telegram & Email simultaneously with zero split logic. | `caspian_agent.py` + `caspian-sdk` |
| 🎯 **Smart Matchmaker** | Dispatches candidates matching a recruiter's explicit tech stack (e.g. `python`, `fastapi`, `react`) and score bar. | `services/matching_engine.py` |
| 🔄 **Webhook Auto-Resolver** | Listens to GitHub push webhooks; LLM checks whether commit diffs resolve open recruiter suggestions. | `routers/webhook.py` |
| 📊 **Dual-Hub Dashboard** | High-performance Streamlit UI with dedicated Student Portfolio, Recruiter Feed, and Admin Diagnostics. | `app.py` + `pages/*.py` |

---

## 🔄 Interactive Data Flow & Architecture

TalentCaspian operates as a multi-tier agentic system connecting **Developers**, **AI Reasoning Engines**, **Caspian Multi-Channel Gateways**, and **Recruiters**.

### 🌟 End-to-End System Pipeline

```mermaid
flowchart TD
    %% Styling Nodes
    classDef studentStyle fill:#1E293B,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC;
    classDef apiStyle fill:#0F172A,stroke:#6366F1,stroke-width:2px,color:#F8FAFC;
    classDef aiStyle fill:#312E81,stroke:#A855F7,stroke-width:2px,color:#F8FAFC;
    classDef dbStyle fill:#064E3B,stroke:#10B981,stroke-width:2px,color:#F8FAFC;
    classDef caspianStyle fill:#701A75,stroke:#EC4899,stroke-width:2px,color:#F8FAFC;
    classDef recruiterStyle fill:#1E293B,stroke:#F59E0B,stroke-width:2px,color:#F8FAFC;

    subgraph StudentLayer ["🎓 1. Developer Layer"]
        Student["Student Developer"]:::studentStyle
        GH_Repo["GitHub Repository / Pushes"]:::studentStyle
    end

    subgraph CoreBackend ["⚡ 2. TalentCaspian Core API (FastAPI)"]
        API["FastAPI Orchestrator<br/>(Port: 8000)"]:::apiStyle
        MatchingEngine["Recruiter Matching Engine"]:::apiStyle
        WebhookHandler["GitHub Webhook Processor"]:::apiStyle
    end

    subgraph IntelligenceLayer ["🧠 3. Intelligence & Database Layer"]
        Gemini["Google Gemini AI<br/>(Repo Analysis & Diff Parsing)"]:::aiStyle
        Postgres[(PostgreSQL DB<br/>Pool: asyncpg)]:::dbStyle
    end

    subgraph CaspianLayer ["✈️ 4. Caspian Multi-Channel Daemon"]
        CaspianDaemon["caspian_agent.py<br/>(Single Unified CommClient)"]:::caspianStyle
        TelegramGateway["Telegram Gateway"]:::caspianStyle
        EmailGateway["Email Gateway"]:::caspianStyle
    end

    subgraph RecruiterLayer ["💼 5. Recruiter Ecosystem"]
        RecruiterTG["Recruiter Telegram App"]:::recruiterStyle
        RecruiterEmail["Recruiter Email Inbox"]:::recruiterStyle
        StreamlitApp["Streamlit Web UI<br/>(Port: 8501)"]:::recruiterStyle
    end

    %% Interactions
    Student -->|1. Register Repo| API
    GH_Repo -->|Webhook Event| WebhookHandler
    API -->|Fetch Code & Tree| GH_Repo
    API -->|Extract Code Analysis| Gemini
    Gemini -->|Score, Summary, Tags| API
    API -->|Save Projects & Scores| Postgres
    
    API -->|Find Matching Recruiters| MatchingEngine
    MatchingEngine -->|Query Preferences| Postgres
    MatchingEngine -->|Trigger Outreach| CaspianDaemon
    
    CaspianDaemon -->|Single Handler Dispatch| TelegramGateway
    CaspianDaemon -->|Single Handler Dispatch| EmailGateway
    TelegramGateway -->|Push Dossier Alert| RecruiterTG
    EmailGateway -->|Push Dossier Alert| RecruiterEmail

    RecruiterTG -->|2-Way Reply: '9/10, Add Docker'| CaspianDaemon
    CaspianDaemon -->|Parse Intent & Rating| Gemini
    Gemini -->|Structured Rating & Note| CaspianDaemon
    CaspianDaemon -->|Save Feedback| Postgres
    
    WebhookHandler -->|Analyze New Push| Gemini
    Gemini -->|Suggestion Resolved: TRUE| WebhookHandler
    WebhookHandler -->|Notify Fix| CaspianDaemon
    CaspianDaemon -->|Instant Resolution Alert| RecruiterTG

    StreamlitApp -->|Read Analytics & Portfolios| API
```

---

### 📡 Sequence Diagram: Real-Time Lifecycle Flow

```mermaid
sequenceDiagram
    autonumber
    actor Dev as 🎓 Student Dev
    participant API as ⚡ FastAPI Backend
    participant GH as 🐙 GitHub API
    participant AI as 🧠 Gemini AI
    participant DB as 🗄️ PostgreSQL
    participant CSP as ✈️ Caspian Agent
    actor Rec as 💼 Recruiter (Telegram)

    Dev->>API: POST /api/register (Repo URL, Name, Email)
    API->>DB: Create Student & Pending Project Record
    API-->>Dev: 201 Created (Background processing enqueued)

    API->>GH: Clone Repo Tree, README & Key Source Files
    GH-->>API: Source Code Content
    API->>AI: analyze_repository(code_payload)
    AI-->>API: AI Score (88/100), Tech Tags (['python', 'fastapi']), Summary
    API->>DB: Save AI metrics to 'projects'

    API->>DB: Match recruiters with tags='python' & min_score <= 88
    DB-->>API: Return Recruiter List
    API->>AI: generate_personalized_recruiter_digest()
    AI-->>API: Tailored 3-sentence pitch
    API->>CSP: Dispatch Outbound Message
    CSP->>Rec: 📲 Deliver Dossier to Telegram!

    Note over Rec,CSP: Bi-Directional Interactive Chat Loop
    Rec->>CSP: Reply: "8/10. Great API design, please add unit tests."
    CSP->>AI: parse_reply_intent("8/10. Great API...")
    AI-->>CSP: {rating: 8, suggestion: "Add unit tests"}
    CSP->>DB: Record rating & insert unresolved suggestion
    CSP-->>Rec: 🤖 "Thank you! Feedback saved and forwarded to student."

    Note over Dev,GH: Developer Fixes the Issue on GitHub
    Dev->>GH: git push origin main ("test: add pytest suite")
    GH->>API: POST /api/webhook/github (Push Event)
    API->>AI: check_resolution(diff, "Add unit tests")
    AI-->>API: {resolved: true, confidence: 0.95}
    API->>DB: UPDATE suggestions SET resolved = TRUE
    API->>CSP: Trigger Resolution Followup
    CSP->>Rec: 🔔 Alert: "Student resolved your suggestion! Unit tests added."
```

---

## 🧮 Deep Scoring Formula

TalentCaspian uses a rigorous two-stage scoring architecture to prevent gaming and reward high-quality code.

### 1. AI Quality Base Score (0–100)
$$\text{AI Score} = (0.40 \times \text{Difficulty}) + (0.30 \times \text{Authenticity}) + (0.30 \times \text{Creativity})$$

* **Difficulty (40%)**: Algorithmic complexity, concurrency, architecture depth, error handling.
* **Authenticity (30%)**: Original commit cadence, absence of boilerplate forks or generic tutorial copies.
* **Creativity (30%)**: Uniqueness of problem statement and novel tech integrations.

### 2. Bayesian Community & Recruiter Adjustment
$$\text{Final Score} = (0.70 \times \text{AI Score}) + (0.30 \times \text{Adjusted Recruiter Rating})$$

$$\text{Adjusted Rating} = \frac{C \times m + \sum R}{C + n}$$
*where $C = 3.0$ (smoothing constant), $m = 70.0$ (prior mean), $n = \text{number of recruiter reviews}$.*

---

## ✈️ Caspian Multi-Channel Engine

TalentCaspian strictly fulfills all hackathon criteria by operating across **Telegram and Email** from a **single unified `on_message` handler**.

```python
# caspian_agent.py — Single Handler Architecture
from caspian_sdk import CommClient, Message

client = CommClient(api_key=os.getenv("CASPIAN_API_KEY"))

# 1. Connect Supported Channels
client.connect_email(username="talentcaspian")
client.connect_telegram(bot_token=os.getenv("TELEGRAM_BOT_TOKEN"))

# 2. Single Unified Message Handler for ALL incoming channels
@client.on_message
async def handle_incoming_message(message: Message):
    logger.info(f"Incoming message from {message.channel}: {message.sender_id}")
    
    # Unified intent extraction & database sync
    response_text = await process_recruiter_interaction(
        channel=message.channel,
        sender_id=message.sender_id,
        content=message.text
    )
    
    await message.reply(response_text)

# 3. Start Multi-Channel Daemon
if __name__ == "__main__":
    client.listen()
```

---

## 🖥️ Live Dashboard & UI

TalentCaspian includes an ultra-responsive, dynamic Streamlit web application running at `http://localhost:8501`.

```
📱 Web Application Directory:
├── 🌐 0_landing.py              ──> Public Hero Showcase, Live Leaderboards & Search
├── 📝 1_student_register.py      ──> GitHub Repo Submission & Real-time AI Scan trigger
├── 🎓 2_student_login.py         ──> Secure Student Portal Authentication
├── 📊 3_student_dashboard.py     ──> Deep Project Analytics, Score Breakdowns & Feedback Tab
├── 🏢 4_recruiter_register.py    ──> Hiring Preference Setup (Tech tags, Min Score, Channel)
├── 💼 5_recruiter_login.py       ──> Recruiter Access & Session Manager
├── 🎯 6_recruiter_dashboard.py   ──> AI Talent Dossier Feed, Direct Rating & Message Dispatch
└── 🛠️ 7_admin_console.py         ──> Webhook Simulator, Worker Health & Database Diagnostics
```

---

## 🚀 Quickstart & Installation

### 📋 Prerequisites
- **Python 3.10+**
- **PostgreSQL 14+** (Local or Supabase / Neon cloud instance)
- **Google Gemini API Key** ([Get one here](https://aistudio.google.com/))
- **Caspian API Key** & **Telegram Bot Token** ([From BotFather](https://t.me/botfather))

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/sayan-majee21/caspian_ai_agent.git
cd caspian_ai_agent
```

### 2️⃣ Create Virtual Environment & Install Dependencies
```bash
# Create virtual environment
python -m venv venv

# Activate on Windows:
venv\Scripts\activate
# Activate on Linux/macOS:
source venv/bin/activate

# Install backend & frontend packages
pip install -r requirements.txt
pip install -r requirements_frontend.txt
```

### 3️⃣ Configure Environment Variables
Copy `.env.example` to `.env` and configure your credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```env
# Database
DATABASE_URL=postgresql://username:password@localhost:5432/talentcaspian

# AI Reasoning
GEMINI_API_KEY=your_google_gemini_api_key

# Caspian Communication Platform
CASPIAN_API_KEY=your_caspian_api_key
CASPIAN_BASE_URL=https://api.trycaspianai.com
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
CASPIAN_EMAIL_USER=your_email@example.com

# GitHub & Security
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret
ADMIN_API_KEY=your_admin_api_key
```

### 4️⃣ Initialize Database Schema & Seed Data
```bash
# Seed initial demo data for students, projects, and recruiters
python -c "import asyncio; from database.db import init_db; asyncio.run(init_db())"
```

---

## 🏃 Running the Services

TalentCaspian consists of three coordinated services:

### 1. Start the FastAPI Core Backend
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
*API Docs available at: `http://localhost:8000/docs`*

### 2. Launch the Streamlit Frontend
```bash
streamlit run app.py
```
*Web application available at: `http://localhost:8501`*

### 3. Run the Caspian Multi-Channel Agent Daemon
```bash
python caspian_agent.py
```
*Listens to incoming Telegram / Email replies and processes auto-resolution loops.*

---

## 📡 API Endpoints

### Core Public & Student APIs
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Health check & system status |
| `POST` | `/api/register` | Register student, save profile & trigger async code audit |
| `GET` | `/api/dashboard` | Fetch project directory, metrics, and recruiter feedback |
| `POST` | `/api/rate` | Submit peer/recruiter rating (1–10) |

### Recruiter & Matching APIs
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/recruiter/register` | Register recruiter preferences (tech tags, min score, channel) |
| `GET` | `/api/recruiter/feed` | Query matched candidates based on hiring criteria |

### Admin & Webhook APIs
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/admin/notify` | Trigger matching algorithm & dispatch outbound Caspian alerts |
| `POST` | `/api/webhook/github` | Receive GitHub push events, verify HMAC & auto-resolve suggestions |

---

## 🧪 Testing & Validation

TalentCaspian includes an extensive test suite verifying backend logic, Caspian handlers, and database operations:

```bash
# Run all automated tests
pytest -v

# Run specific feature tests
pytest tests/test_caspian_integration.py
pytest tests/test_scoring.py
pytest tests/test_webhook.py
```

---

## 👥 Hackathon Submission Details

- **Hackathon**: Caspian AI Agent Hackathon (15-Day Challenge)
- **Built By**: Sayan Majee ([@sayan-majee21](https://github.com/sayan-majee21))
- **Track**: Autonomous Multi-Channel Agent with Single Handler (`caspian-sdk`)
- **Supported Channels**: Telegram & Email

---

<div align="center">
  <sub>Built with ❤️ using <strong>Caspian SDK</strong>, <strong>FastAPI</strong>, <strong>Gemini AI</strong>, and <strong>Streamlit</strong>.</sub>
</div>
