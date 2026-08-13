# 🔄 TalentCaspian — Data Flow & API Architecture Guide (Visual & Simplified)

Welcome to the **TalentCaspian Architecture Guide**! This document explains in clear, visual, and non-overly-technical terms:
1. **How data flows** through the system.
2. **Where information is stored** in the database.
3. **When API calls happen** (GitHub, Google Gemini AI, Telegram).

---

## 🌟 1. The Big Picture: How TalentCaspian Works in 4 Steps

```mermaid
flowchart LR
    Step1["1. Student Submits Repo"] --> Step2["2. AI Scans & Rates Code"]
    Step2 --> Step3["3. Recruiter Gets Telegram Alert"]
    Step3 --> Step4["4. Recruiter Replies & Loop Closes"]
```

1. **Student Registers**: A student signs up with their GitHub repository link.
2. **Agent 1 (Portfolio Scanner)**: Fetches code from GitHub and uses Google Gemini AI to evaluate code quality (0–100 score) and extract tech tags (e.g. `python`, `fastapi`).
3. **Agent 2 (Recruiter Matcher)**: Matches high-quality projects with recruiters based on tech preferences and sends a personalized alert to the recruiter's Telegram app.
4. **Agent 3 (Recruiter Reply Listener)**: Recruiter replies directly on Telegram with a rating (e.g. `9/10`) or suggestion (`"Add Docker setup"`). When the student fixes it on GitHub, TalentCaspian automatically detects the fix and alerts the recruiter!

---

## 🔄 2. Complete Data Flow & API Call Diagrams

### Diagram A: From Student Registration to Recruiter Telegram Alert

```mermaid
sequenceDiagram
    autonumber
    actor Student as 🎓 Student
    participant API as ⚡ FastAPI Server
    participant DB as 🗄️ PostgreSQL DB
    participant GH as 🐙 GitHub API
    participant GEM as 🧠 Gemini AI API
    actor Recruiter as 💼 Recruiter (Telegram)
    participant CASP as ✈️ Caspian Telegram SDK

    Student->>API: 1. Register Student & Repo URL (/api/register)
    API->>DB: Save Student & Project Records
    API-->>Student: 2. Instant 201 Created Response

    note over API,GH: Background Processing Starts

    API->>GH: 3. Fetch repo files, README & commit history
    GH-->>API: Return repository code & metadata
    API->>GEM: 4. Send code to Gemini Flash for evaluation
    GEM-->>API: Return AI Score (0-100), Tags & Summary
    API->>DB: Save AI Score, Tech Tags & Summary to 'projects' table

    note over API,CASP: Recruiter Matching & Notification

    API->>DB: Query recruiters matching tech stack & min score
    API->>GEM: 5. Generate personalized message for recruiter
    GEM-->>API: Return 2-3 sentence notification text
    API->>CASP: 6. Send message to Telegram Bot
    CASP->>Recruiter: 7. Deliver message to Recruiter's Telegram App!
    API->>DB: Log message in 'notification_logs' table
```

---

### Diagram B: Recruiter Telegram Reply & Automatic Code Push Resolution Loop

```mermaid
sequenceDiagram
    autonumber
    actor Recruiter as 💼 Recruiter (Telegram Phone)
    participant Daemon as 🎧 caspian_agent.py Daemon
    participant API as ⚡ FastAPI Server
    participant DB as 🗄️ PostgreSQL DB
    participant GEM as 🧠 Gemini AI API
    actor Student as 🎓 Student (GitHub)
    participant GH as 🐙 GitHub Webhook

    Recruiter->>Daemon: 1. Send Telegram Reply: "9/10. Add Docker setup"
    Daemon->>DB: Lookup Recruiter & Latest Notified Project
    Daemon->>GEM: 2. Parse reply intent, rating (9) & suggestion
    GEM-->>Daemon: Return structured rating & suggestion text
    Daemon->>DB: Save rating in 'project_ratings' & suggestion in 'suggestions' table
    Daemon->>DB: Recalculate & update project 'final_score'

    note over Student,GH: Student Resolves Feedback on GitHub

    Student->>GH: 3. Push commit: "feat: add Dockerfile and docker-compose"
    GH->>API: 4. POST Webhook event (/api/webhook/github)
    API->>DB: Verify signature & check idempotency ('processed_deliveries')
    API->>GEM: 5. Is push Major or Minor?
    GEM-->>API: "Major"
    API->>GEM: 6. Does push resolve "Add Docker setup"?
    GEM-->>API: {"resolved": true}
    API->>DB: Update 'suggestions' table SET resolved = True
    API->>Daemon: 7. Trigger follow-up notification
    Daemon->>Recruiter: 8. Instant Telegram Alert: "Student resolved your Docker feedback!"
```

---

## 🗄️ 3. Where Information Gets Saved (PostgreSQL Tables Made Simple)

TalentCaspian stores data in **7 easy-to-understand database tables**:

| Table Name | What it Stores | Key Fields |
| :--- | :--- | :--- |
| 🧑‍🎓 **`students`** | Student profile details | Student ID, Name, Email, GitHub Username |
| 📁 **`projects`** | Portfolio projects & AI quality scores | Project ID, Student ID, GitHub Repo URL, AI Score, Final Score, Tech Tags, Summary |
| 👔 **`recruiters`** | Recruiter profiles & hiring preferences | Recruiter ID, Name, Email, Channel (`telegram`), Preferred Tech Stack & Min Score |
| ⭐ **`project_ratings`** | 1 to 10 ratings given by recruiters & peers | Rating ID, Project ID, Rater Type, Rating Score (1-10) |
| 💡 **`suggestions`** | Recruiter feedback & code improvement notes | Suggestion ID, Project ID, Recruiter ID, Feedback Text, Resolved (`true`/`false`) |
| 📜 **`notification_logs`** | History of sent alerts (prevents spamming) | Log ID, Recruiter ID, Project ID, Channel, Message Text, Sent Timestamp |
| 🔒 **`processed_deliveries`**| GitHub webhook IDs (prevents duplicate pushes) | Delivery UUID, Processed Timestamp |

---

## 🌐 4. When API Calls Happen

### A. Internal API Endpoints (Used by Frontend & Admin)

- **`POST /api/register`**: Registers a student and triggers background GitHub code scanning.
- **`GET /api/dashboard`**: Fetches portfolio projects for the student dashboard.
- **`POST /api/rate`**: Allows peers to rate a project 1-10.
- **`POST /api/recruiter/register`**: Saves recruiter hiring preferences.
- **`POST /api/admin/notify`**: Triggers recruiter matching and sends Telegram alerts.
- **`POST /api/webhook/github`**: Receives GitHub push notifications when students update code.

---

### B. External API Calls (Connected Third-Party Services)

#### 1. GitHub API (`https://api.github.com`)
- **When it runs**: When a student registers or pushes new code to GitHub.
- **What it does**: Reads directory files, README content, and commit messages.

#### 2. Google Gemini AI API (`google-genai` SDK)
- **When it runs**: 
  - Evaluating code quality (`ai_score` 0-100).
  - Generating personalized recruiter alerts.
  - Parsing Telegram replies (extracting ratings and suggestions).
  - Checking if a GitHub push fixed a recruiter's suggestion.

#### 3. Caspian Telegram SDK (`caspian_sdk`)
- **When it runs**: 
  - Sending outbound Telegram messages to recruiters' phones.
  - Running a background listener (`caspian_agent.py`) to receive incoming Telegram replies.

---

## 📊 5. How Project Scores Work (Simple Math)

A project's quality is represented by two simple scores:

1. **AI Quality Score (0–100)**:  
   $$\text{AI Score} = (40\% \times \text{Difficulty}) + (30\% \times \text{Authenticity}) + (30\% \times \text{Creativity})$$

2. **Final Overall Score (0–100)**:  
   $$\text{Final Score} = (70\% \times \text{AI Score}) + (30\% \times \text{Recruiter/Peer Ratings})$$

This ensures high-quality projects rank top on the recruiter feed!
