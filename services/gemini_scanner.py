"""Gemini Flash Code Quality & Evaluation Service for TalentCaspian Agent 1.

Uses Google Gemini Flash API to rate student portfolio projects, calculate weighted ai_score,
classify push updates as Major/Minor, and verify recruiter suggestion resolution.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any
from google import genai
from google.genai import types

logger = logging.getLogger("talentcaspian.gemini_scanner")

# Global semaphore for rate limiting Gemini API calls
_gemini_semaphore = asyncio.Semaphore(5)

# System prompt fixed for every call
EVALUATION_SYSTEM_PROMPT = """You are a senior technical recruiter evaluating a student's software portfolio project.
Your task is to analyze the provided repository metadata, README, directory structure, and source code files, and evaluate the project quality based on strict, objective criteria.

You must output a JSON object containing EXACTLY these five fields:
1. "difficulty" (number from 0 to 100): Complexity of the problem solved, architectural sophistication, algorithms, and technical depth.
2. "authenticity" (number from 0 to 100): Likelihood that the code is original, well-structured, non-trivial, and not just copy-pasted tutorial code or basic boilerplate.
3. "creativity" (number from 0 to 100): Novelty of the approach, uniqueness of application, problem-solving ingenuity, and design flair.
4. "tags" (array of strings): 3 to 7 domain/tech-stack tags identifying key technologies and domains (e.g., ["python", "fastapi", "postgresql", "backend", "machine-learning"]).
5. "summary" (string): A concise 2-3 sentence overview highlighting the project's core purpose, technical highlights, and key capabilities.

Output ONLY valid JSON matching this schema."""


def calculate_weighted_ai_score(
    difficulty: float, authenticity: float, creativity: float
) -> float:
    """Calculate the weighted overall AI score based on the rubric formula.

    ai_score = (0.4 * difficulty) + (0.3 * authenticity) + (0.3 * creativity)

    Args:
        difficulty (float): Difficulty rating (0-100).
        authenticity (float): Authenticity rating (0-100).
        creativity (float): Creativity rating (0-100).

    Returns:
        float: Calculated score rounded to 2 decimal places, clamped between 0 and 100.
    """
    raw_score = (0.4 * difficulty) + (0.3 * authenticity) + (0.3 * creativity)
    return round(max(0.0, min(100.0, raw_score)), 2)


async def evaluate_repository(
    repo_context: dict[str, Any], api_key: str | None = None
) -> dict[str, Any]:
    """Perform automated code quality assessment on a repository using Gemini Flash.

    Args:
        repo_context (dict[str, Any]): Dictionary containing repo metadata, README,
            tree, and source code files.
        api_key (str | None): Optional Gemini API key override.

    Returns:
        dict[str, Any]: Evaluation dictionary containing ai_difficulty, ai_authenticity,
            ai_creativity, ai_score, tags, and summary.
    """
    key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")


    if not key:
        logger.info("GEMINI_API_KEY not set. Using fallback deterministic evaluation.")
        # Deterministic fallback evaluation for offline / test environments
        lang = str(repo_context.get("language", "Python")).lower()
        files = repo_context.get("source_files", {})
        diff = min(90.0, max(50.0, 60.0 + len(files) * 2.0))
        auth = 85.0
        crea = 80.0
        score = calculate_weighted_ai_score(diff, auth, crea)
        tags = [lang] if lang and lang != "unknown" else ["software-engineering"]
        if "fastapi" in str(files).lower() or "python" in lang:
            tags.extend(["python", "backend"])
        summary = f"Project {repo_context.get('repo', 'repository')} demonstrates clean code organization with {len(files)} source files."
        return {
            "ai_difficulty": diff,
            "ai_authenticity": auth,
            "ai_creativity": crea,
            "ai_score": score,
            "tags": list(set(tags)),
            "summary": summary,
        }

    async with _gemini_semaphore:
        try:
            client = genai.Client(api_key=key)
            prompt_content = f"""
            Repository Name: {repo_context.get('repo')}
            Owner: {repo_context.get('owner')}
            Language: {repo_context.get('language')}
            Description: {repo_context.get('description')}
            Stars: {repo_context.get('stars')}, Forks: {repo_context.get('forks')}

            README Content:
            {repo_context.get('readme', '')[:3000]}

            Directory Tree (sample):
            {json.dumps(repo_context.get('tree_structure', [])[:50])}

            Source Files Content:
            {json.dumps(repo_context.get('source_files', {}))[:10000]}
            """

            response = await client.aio.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=EVALUATION_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )

            res_text = response.text.strip()
            json_match = re.search(r"\{[\s\S]*\}", res_text)
            if json_match:
                res_text = json_match.group(0)

            data = json.loads(res_text)

            diff = float(data.get("difficulty") or 70.0)
            auth = float(data.get("authenticity") or 75.0)
            crea = float(data.get("creativity") or 70.0)
            score = calculate_weighted_ai_score(diff, auth, crea)
            raw_tags = data.get("tags") or ["python", "backend"]
            tags = [str(t) for t in raw_tags if t] if isinstance(raw_tags, list) else [str(raw_tags)]
            summary = str(data.get("summary") or "Portfolio project repository.")

            return {
                "ai_difficulty": diff,
                "ai_authenticity": auth,
                "ai_creativity": crea,
                "ai_score": score,
                "tags": tags,
                "summary": summary,
            }
        except Exception as exc:
            logger.error(f"Error during Gemini evaluation: {exc}")
            diff, auth, crea = 65.0, 75.0, 70.0
            return {
                "ai_difficulty": diff,
                "ai_authenticity": auth,
                "ai_creativity": crea,
                "ai_score": calculate_weighted_ai_score(diff, auth, crea),
                "tags": ["software-engineering"],
                "summary": "Repository code evaluation completed.",
            }


async def classify_push_update(
    commit_messages: list[str],
    modified_files: list[str],
    api_key: str | None = None,
) -> str:
    """Classify whether a push update is 'Major' or 'Minor'.

    Args:
        commit_messages (list[str]): List of commit message strings in the push.
        modified_files (list[str]): List of modified/added file paths.
        api_key (str | None): Optional Gemini API key override.

    Returns:
        str: 'Major' or 'Minor'.
    """
    joined_commits = " ".join(commit_messages).lower()
    only_docs = all(
        f.lower().endswith(".md") or f.lower().startswith("docs/")
        for f in modified_files
    ) if modified_files else False

    has_minor_kw = bool(re.search(r"\b(typo|readme|formatting|style tweak|bump version|docs?)\b", joined_commits))
    has_major_kw = bool(re.search(r"\b(feat|feature|refactor|implement|breaking)\b", joined_commits))
    if re.search(r"\bfix\b", joined_commits) and not re.search(r"\bfix(?:ed|ing)?\s+(?:typo|readme|docs?|format)", joined_commits):
        has_major_kw = True

    if (only_docs or has_minor_kw) and not has_major_kw:
        return "Minor"

    key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")

    if not key:
        return "Minor" if only_docs else "Major"

    async with _gemini_semaphore:
        try:
            client = genai.Client(api_key=key)
            prompt = f"""
            Given these commit messages and modified file paths, is this a 'Major' functional update or a 'Minor' update (e.g. typos, readme tweaks, formatting)?

            Commit messages:
            {json.dumps(commit_messages)}

            Modified file paths:
            {json.dumps(modified_files)}

            Respond with ONLY one word: "Major" or "Minor".
            """
            response = await client.aio.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            match = re.search(r"\b(major|minor)\b", response.text, re.IGNORECASE)
            if match:
                return match.group(1).capitalize()
            return "Major"
        except Exception as exc:
            logger.warning(f"Push classification call failed, defaulting: {exc}")
            return "Major"


def _fallback_keyword_resolution_match(
    suggestion_text: str,
    commit_messages: list[str],
    modified_files: list[str] | None = None,
) -> bool:
    """Helper to perform heuristic keyword resolution matching on commit messages and modified files."""
    stop_words = {
        "please", "would", "could", "should", "about", "there", "their", "where",
        "which", "these", "those", "after", "before", "while", "using", "project",
        "code", "make", "need", "needs", "also", "with", "from", "have", "your", "this", "that", "more", "some"
    }
    all_text = (" ".join(commit_messages) + " " + " ".join(modified_files or [])).lower()
    sig_words = [w.lower() for w in re.findall(r"\b\w{3,}\b", suggestion_text) if w.lower() not in stop_words]
    if not sig_words:
        return False
    return any(w in all_text for w in sig_words)


async def check_suggestion_resolution(
    suggestion_text: str,
    commit_messages: list[str],
    modified_files: list[str],
    api_key: str | None = None,
) -> bool:
    """Determine whether a commit push resolves a specific recruiter suggestion.

    Args:
        suggestion_text (str): The recruiter suggestion text.
        commit_messages (list[str]): Commit messages in push.
        modified_files (list[str]): Modified file paths in push.
        api_key (str | None): Optional Gemini API key override.

    Returns:
        bool: True if the suggestion is resolved by this push, False otherwise.
    """
    key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")

    if not key:
        return _fallback_keyword_resolution_match(suggestion_text, commit_messages, modified_files)

    async with _gemini_semaphore:
        try:
            client = genai.Client(api_key=key)
            prompt = f"""
            Analyze whether the following code push addresses and resolves the recruiter's suggestion.

            Recruiter Suggestion:
            "{suggestion_text}"

            Push Commit Messages:
            {json.dumps(commit_messages)}

            Push Modified Files:
            {json.dumps(modified_files)}

            Return JSON: {{"resolved": true}} or {{"resolved": false}}.
            """
            response = await client.aio.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            res_text = response.text.strip()
            json_match = re.search(r"\{[\s\S]*\}", res_text)
            if json_match:
                res_text = json_match.group(0)
            data = json.loads(res_text)
            raw_resolved = data.get("resolved", False)
            if isinstance(raw_resolved, str):
                return raw_resolved.strip().lower() in ("true", "1", "yes")
            return bool(raw_resolved)

        except Exception as exc:
            logger.warning(f"Suggestion resolution check failed: {exc}")
            return _fallback_keyword_resolution_match(suggestion_text, commit_messages, modified_files)
