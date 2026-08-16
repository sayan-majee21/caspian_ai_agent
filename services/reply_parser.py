"""Gemini Flash & Regex Natural Language Reply Parser for Caspian Recruiter Replies.

Parses incoming recruiter replies to classify intent (suggestion, rating, inquiry)
and extract actionable details (suggestion text, numerical rating 1-10).
"""

import asyncio
import json
import logging
import os
import re
from typing import Any
from google import genai
from google.genai import types


logger = logging.getLogger("talentcaspian.reply_parser")



# Global semaphore for rate limiting Gemini API calls
_gemini_semaphore = asyncio.Semaphore(5)


def parse_reply_with_regex(text: str) -> dict[str, Any]:

    """Fallback natural language parsing using regex and keyword matching.

    Args:
        text (str): Incoming message body text.

    Returns:
        dict[str, Any]: Extracted intent, suggestion_text, and rating.
    """
    result: dict[str, Any] = {
        "intent": "noise",
        "suggestion_text": None,
        "rating": None,
    }
    if not text:
        return result

    clean_text = text.strip()

    # 1. Rating extraction
    # Patterns: 8/10, 8 out of 10, rating: 8, 8 stars
    rating_patterns = [
        r"(?:rating|score)[:\s]*(\b10|\b[1-9])(?:\s*/\s*10|\s*out of 10)?",
        r"\b([1-9]|10)\s*(?:/\s*10|out of 10)\b",
        r"\b([1-9]|10)\s*stars?\b",
        r"(\b10|\b[1-9])\s*/\s*10",
    ]
    extracted_rating = None
    for pattern in rating_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            try:
                val = int(match.group(1))
                if 1 <= val <= 10:
                    extracted_rating = val
                    break
            except (ValueError, IndexError):
                pass

    if extracted_rating is not None:
        result["rating"] = extracted_rating

    # 2. Suggestion extraction
    sug_prefix_match = re.search(
        r"(?:suggest|suggestion|feedback)[:\s]+(.+)", clean_text, re.IGNORECASE | re.DOTALL
    )
    if sug_prefix_match:
        result["suggestion_text"] = sug_prefix_match.group(1).strip()
    else:
        suggestion_keywords = [
            "suggest", "add", "fix", "update", "change", "improve",
            "issue", "should", "needs", "need", "please add", "please fix",
            "bug", "refactor", "documentation", "readme", "docker", "unit test"
        ]
        lower_text = clean_text.lower()
        if any(kw in lower_text for kw in suggestion_keywords):
            result["suggestion_text"] = clean_text

    # Set intent
    has_sug = bool(result["suggestion_text"])
    has_rat = result["rating"] is not None

    if has_sug and has_rat:
        result["intent"] = "both"
    elif has_sug:
        result["intent"] = "suggestion"
    elif has_rat:
        result["intent"] = "rating"
    else:
        result["intent"] = "noise"

    return result


async def parse_recruiter_reply(
    text: str, api_key: str | None = None
) -> dict[str, Any]:
    """Parse incoming recruiter reply using Gemini Flash with regex fallback.

    Args:
        text (str): Incoming natural language reply text.
        api_key (str | None): Optional Gemini API key override.

    Returns:
        dict[str, Any]: Dictionary containing intent ('suggestion'|'rating'|'both'|'noise'),
            suggestion_text (str | None), and rating (int | None).
    """
    if not text or not text.strip():
        return {"intent": "noise", "suggestion_text": None, "rating": None}

    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        logger.info("GEMINI_API_KEY not configured. Falling back to regex parsing.")
        return parse_reply_with_regex(text)

    prompt = f"""You are an AI assistant analyzing a recruiter's response to a candidate's portfolio.
Analyze the following recruiter message and extract structured intent:

Recruiter Message:
"{text}"

Output a valid JSON object matching this schema:
{{
  "intent": "suggestion" | "rating" | "both" | "noise",
  "suggestion_text": string or null (extract specific improvement/code/feature suggestion if present),
  "rating": integer between 1 and 10 or null (extract numeric score out of 10 if present)
}}

Output ONLY the JSON object, with no markdown formatting or extra commentary."""

    try:
        async with _gemini_semaphore:
            client = genai.Client(api_key=key)
            response = await client.aio.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            raw_output = response.text.strip()


        # Clean code block backticks if present
        if raw_output.startswith("```"):
            lines = raw_output.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_output = "\n".join(lines).strip()

        data = json.loads(raw_output)

        intent = data.get("intent", "noise")
        sug_text = data.get("suggestion_text")
        rating_val = data.get("rating")

        # Validate rating
        if rating_val is not None:
            try:
                rating_val = int(rating_val)
                if not (1 <= rating_val <= 10):
                    rating_val = None
            except (ValueError, TypeError):
                rating_val = None

        if sug_text and not isinstance(sug_text, str):
            sug_text = str(sug_text)

        return {
            "intent": intent,
            "suggestion_text": sug_text if sug_text else None,
            "rating": rating_val,
        }

    except Exception as exc:
        logger.warning("Gemini parsing failed (%s). Falling back to regex parser.", exc)
        return parse_reply_with_regex(text)
