"""Personalized Outreach Generator Service for TalentCaspian Agent 2.

Utilizes the Gemini Flash API to craft brief, tailored notification messages for recruiters,
highlighting project quality, matching tags, and student dashboard links.
"""

import asyncio
import logging
import os
from typing import Any

from google import genai
from google.genai import types

logger = logging.getLogger("talentcaspian.outreach_service")

# Global semaphore for rate limiting Gemini API calls
_gemini_semaphore = asyncio.Semaphore(5)

OUTREACH_SYSTEM_PROMPT = """You are an outbound recruiter communications assistant for TalentCaspian.
Your job is to generate a brief, professional, compelling 2-3 sentence notification message for a tech recruiter.
Highlight why the student's portfolio project fits the recruiter's tech stack and skill interests.
The message must be concise (like a notification alert, NOT a verbose essay) and include the student name, repository link, matching technologies, project summary, and dashboard link.
"""


def _get_matching_tags(recruiter: dict[str, Any], project: dict[str, Any]) -> list[str]:
    """Helper to extract overlapping tech stack tags between recruiter and project."""
    pref = recruiter.get("preference_filters") or {}
    if isinstance(pref, str):
        import json
        try:
            pref = json.loads(pref)
        except Exception:
            pref = {}

    recruiter_stack = [t.lower() for t in pref.get("tech_stack", []) if isinstance(t, str)]
    project_tags = project.get("tags") or []
    if isinstance(project_tags, str):
        import json
        try:
            project_tags = json.loads(project_tags)
        except Exception:
            project_tags = []

    project_tags_lower = [t.lower() for t in project_tags if isinstance(t, str)]

    if not recruiter_stack:
        return [t for t in project_tags if isinstance(t, str)]

    matched = [t for t in project_tags if isinstance(t, str) and t.lower() in recruiter_stack]
    return matched if matched else [t for t in project_tags if isinstance(t, str)]


async def generate_outreach_message(
    recruiter: dict[str, Any],
    project: dict[str, Any],
    api_key: str | None = None,
) -> str:
    """Generate a brief, tailored recruiter notification message using Gemini Flash API.

    Args:
        recruiter (dict[str, Any]): Recruiter record dictionary.
        project (dict[str, Any]): Project record dictionary with student metadata.
        api_key (str | None): Optional Gemini API key override.

    Returns:
        str: Generated notification message text.
    """
    recruiter_name = recruiter.get("name", "Recruiter")
    student_name = project.get("student_name", "Student")
    repo_url = project.get("repo_url", "https://github.com/example/project")
    summary = project.get("summary", "High-quality portfolio project.")
    matching_tags = _get_matching_tags(recruiter, project)
    tags_str = ", ".join(matching_tags) if matching_tags else "general engineering"
    dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000/dashboard")

    key = api_key or os.getenv("GEMINI_API_KEY")

    if not key:
        logger.info("GEMINI_API_KEY not set. Using fallback outreach message generator.")
        return (
            f"Hi {recruiter_name}, student {student_name}'s project ({repo_url}) matches your interest in {tags_str}! "
            f"Summary: {summary} Check details on TalentCaspian Dashboard: {dashboard_url}"
        )

    async with _gemini_semaphore:
        try:
            client = genai.Client(api_key=key)
            prompt = f"""
            Recruiter Name: {recruiter_name}
            Student Name: {student_name}
            Repository URL: {repo_url}
            Matching Technologies: {tags_str}
            Project Summary: {summary}
            Dashboard Link: {dashboard_url}

            Generate a concise, professional notification message for {recruiter_name}.
            """

            response = await client.aio.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=OUTREACH_SYSTEM_PROMPT,
                    temperature=0.3,
                ),
            )
            msg = response.text.strip()
            if msg:
                return msg
        except Exception as exc:
            logger.warning(f"Gemini API call failed for outreach generation: {exc}. Using fallback.")


    return (
        f"Hi {recruiter_name}, student {student_name}'s project ({repo_url}) matches your interest in {tags_str}! "
        f"Summary: {summary} Check details on TalentCaspian Dashboard: {dashboard_url}"
    )


def generate_followup_message(
    recruiter: dict[str, Any],
    project: dict[str, Any],
    suggestion_text: str,
) -> str:
    """Generate a direct follow-up notification message when a student resolves a recruiter's feedback.

    Args:
        recruiter (dict[str, Any]): Recruiter record dictionary.
        project (dict[str, Any]): Project record dictionary with student metadata.
        suggestion_text (str): Recruiter's original suggestion text.

    Returns:
        str: Formatted follow-up notification string.
    """
    recruiter_name = recruiter.get("name", "Recruiter")
    student_name = project.get("student_name", "Student")
    project_name = project.get("repo_url", "the project").rstrip("/").split("/")[-1]

    return (
        f"Hi {recruiter_name}, Student {student_name} has updated '{project_name}' "
        f"addressing your feedback regarding {suggestion_text}!"
    )
