---
name: portfolio-helper
description: Seeds realistic dummy data (students, projects, and recruiters) in the PostgreSQL database for the TalentCaspian project.
---

# TalentCaspian Seeding Helper

This helper seeds mock data into the PostgreSQL database.

## Usage Guide
Run the skill with one of the following commands:
- `/portfolio-helper seed students` (seeds mock student profiles with GitHub/Kaggle usernames)
- `/portfolio-helper seed recruiters` (seeds mock recruiters with contact channels and rating filters)
- `/portfolio-helper seed projects` (seeds mock repositories with scores, categories, metrics, and write-ups)
- `/portfolio-helper seed all` (seeds students, recruiters, and projects in relational order)

---

## Technical Details

- **Database Connection**: Reads connection credentials (`DATABASE_URL`) from the `.env` file and uses a PostgreSQL connection pool.
- **Relational Integrity**: Seeds students first, then recruiters, and finally projects and suggestions to satisfy foreign key dependencies.
- **Random Data Generation**: 
  - Projects: Generates realistic GitHub/Kaggle repository URLs and categories (AI/ML, Web Dev, Data Science).
  - Ratings & Metrics: Assigns mock scores (60-95) and populates JSONB metrics (e.g. Code Quality, Documentation, Innovation).
  - Recruiters: Assigns channel details (Email/Telegram/Slack) and filter preferences matching the project scores and categories.
