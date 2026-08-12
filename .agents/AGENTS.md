# TalentCaspian Coding Standards

These rules apply to all code in the TalentCaspian repository.

## Python (FastAPI & Caspian)
- Use **Type Hints** and descriptive docstrings for all router functions and API parameters.
- Follow **PEP 8** strictly.
- Database connections should be managed using context managers or FastAPI dependency injection (`Depends`) to guarantee prompt release of connections back to the PostgreSQL pool.
- Never use blocking synchronous calls (like `time.sleep` or synchronous requests) in async endpoints; use `asyncio.sleep` or background threads.
- Run the Caspian `CommClient` listener loop in a separate worker process or thread pool rather than blocking the FastAPI main event loop.

## HTML/CSS/JS (React & Tailwind)
- Use Tailwind CSS classes for styling. Avoid writing custom inline CSS.
- Ensure all pages are responsive and mobile-friendly.
- Components should be modular, clean, and reusable. Avoid monolithic React components.

## Git
- Branch names should be descriptive (e.g., `feature/postgres-schema` or `feature/caspian-integration`).
- Commit messages must follow the Conventional Commits prefix convention: "feat:", "fix:", or "docs:".
