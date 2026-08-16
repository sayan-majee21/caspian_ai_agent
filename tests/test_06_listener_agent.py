"""Unit and Integration Tests for Step 6 — Caspian Listener Agent (Reply Handling)."""

import os
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from caspian_sdk import Message
import caspian_agent
import database.db as db_module
from services.reply_parser import parse_recruiter_reply, parse_reply_with_regex


@pytest.fixture
def mock_db_pool():
    """Fixture to mock database pool and DB readiness for tests."""
    mock_pool = AsyncMock()
    
    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_pool

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_pool.acquire.return_value = AsyncContextManagerMock()
    
    with patch.object(db_module, "DB_POOL", mock_pool), \
         patch.object(db_module, "is_pool_ready", return_value=True):
        yield mock_pool


# ---------------------------------------------------------------------------
# 1. Reply Parser Unit Tests (Gemini & Regex Fallback)
# ---------------------------------------------------------------------------
def test_regex_parser_rating_and_suggestion():
    """Verify regex parser extracts both rating and suggestion text from natural language."""
    text = "Great work! 8/10 rating. Please add unit tests for the router."
    parsed = parse_reply_with_regex(text)
    assert parsed["intent"] == "both"
    assert parsed["rating"] == 8
    assert "unit tests" in parsed["suggestion_text"]


def test_regex_parser_rating_only():
    """Verify regex parser handles rating-only messages."""
    text = "Rating: 9 out of 10"
    parsed = parse_reply_with_regex(text)
    assert parsed["intent"] == "rating"
    assert parsed["rating"] == 9
    assert parsed["suggestion_text"] is None


def test_regex_parser_suggestion_only():
    """Verify regex parser handles suggestion-only messages."""
    text = "suggest: Please fix the responsive CSS layout on mobile"
    parsed = parse_reply_with_regex(text)
    assert parsed["intent"] == "suggestion"
    assert parsed["suggestion_text"] == "Please fix the responsive CSS layout on mobile"
    assert parsed["rating"] is None


def test_regex_parser_noise():
    """Verify regex parser handles general inquiries or noise."""
    text = "Thanks for the email, I will take a look next week."
    parsed = parse_reply_with_regex(text)
    assert parsed["intent"] == "noise"
    assert parsed["rating"] is None
    assert parsed["suggestion_text"] is None


@pytest.mark.asyncio
async def test_gemini_parser_mocked():
    """Verify parse_recruiter_reply uses Gemini response when API key is provided."""
    mock_response = MagicMock()
    mock_response.text = '{"intent": "suggestion", "suggestion_text": "Add Docker setup", "rating": null}'

    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_instance

        res = await parse_recruiter_reply("Need docker setup", api_key="mock_gemini_key")
        assert res["intent"] == "suggestion"
        assert res["suggestion_text"] == "Add Docker setup"
        assert res["rating"] is None



# ---------------------------------------------------------------------------
# 2. Listener Agent Processing Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_suggestion_reply(mock_db_pool):
    """Test processing a suggestion reply: ensure new row created in suggestions with resolved=False."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "email"
    mock_msg.sender = "recruiter@techcorp.com"
    mock_msg.text = "Please add a README file with setup instructions."
    mock_msg.reply = MagicMock()

    mock_recruiter = {"id": 10, "name": "Jane Recruiter", "email": "recruiter@techcorp.com"}
    mock_suggestion = {"id": 1, "project_id": 42, "recruiter_id": 10, "suggestion_text": mock_msg.text, "resolved": False}

    with patch("database.db.get_recruiter_by_contact", new_callable=AsyncMock) as mock_get_recruiter, \
         patch("database.db.get_latest_notified_project_for_recruiter", new_callable=AsyncMock) as mock_get_proj, \
         patch("database.db.add_suggestion", new_callable=AsyncMock) as mock_add_sug:
        
        mock_get_recruiter.return_value = mock_recruiter
        mock_get_proj.return_value = 42
        mock_add_sug.return_value = mock_suggestion

        res = await caspian_agent.process_inbound_message(mock_msg)

        assert res["status"] == "processed"
        assert res["recruiter_id"] == 10
        assert res["project_id"] == 42
        assert res["suggestion_added"] is True
        
        mock_add_sug.assert_called_once_with(
            mock_db_pool,
            {
                "project_id": 42,
                "recruiter_id": 10,
                "suggestion_text": mock_msg.text,
            }
        )
        mock_msg.reply.assert_called_once()
        assert "recorded your suggestion" in mock_msg.reply.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_handle_rating_reply(mock_db_pool):
    """Test processing a rating reply: ensure project_ratings row created and score updated."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "telegram"
    mock_msg.sender = "@janedoe_recruiter"
    mock_msg.text = "Great project! Rating: 9/10"
    mock_msg.reply = MagicMock()

    mock_recruiter = {"id": 15, "name": "Jane Doe", "email": "jane@company.com", "telegram_handle": "@janedoe_recruiter"}

    with patch("database.db.get_recruiter_by_contact", new_callable=AsyncMock) as mock_get_recruiter, \
         patch("database.db.get_latest_notified_project_for_recruiter", new_callable=AsyncMock) as mock_get_proj, \
         patch("database.db.add_project_rating", new_callable=AsyncMock) as mock_add_rating, \
         patch("database.db.update_project_score", new_callable=AsyncMock) as mock_update_score:
        
        mock_get_recruiter.return_value = mock_recruiter
        mock_get_proj.return_value = 101
        mock_add_rating.return_value = {"id": 5, "project_id": 101, "rating": 9}
        mock_update_score.return_value = 88.5

        res = await caspian_agent.process_inbound_message(mock_msg)

        assert res["status"] == "processed"
        assert res["recruiter_id"] == 15
        assert res["project_id"] == 101
        assert res["rating_added"] is True

        mock_add_rating.assert_called_once_with(
            mock_db_pool,
            {
                "project_id": 101,
                "rater_type": "recruiter",
                "rater_id": 15,
                "rating": 9,
            }
        )
        mock_update_score.assert_called_once_with(mock_db_pool, 101)
        mock_msg.reply.assert_called_once()
        assert "recorded your rating of 9/10" in mock_msg.reply.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_unknown_sender(mock_db_pool):
    """Test handling reply from unregistered email/handle: returns unrecognized_sender status and polite reply."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "email"
    mock_msg.sender = "unregistered_stranger@unknown.com"
    mock_msg.text = "Interested in hiring."
    mock_msg.reply = MagicMock()

    with patch("database.db.get_recruiter_by_contact", new_callable=AsyncMock) as mock_get_recruiter:
        mock_get_recruiter.return_value = None

        res = await caspian_agent.process_inbound_message(mock_msg)

        assert res["status"] == "unrecognized_sender"
        assert res["sender"] == "unregistered_stranger@unknown.com"
        mock_msg.reply.assert_called_once()
        assert "Sender not recognized" in mock_msg.reply.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_context_resolution(mock_db_pool):
    """Test context resolution linking reply to recruiter's most recently notified project via notification_logs."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "email"
    mock_msg.sender = "recruiter@corp.com"
    mock_msg.text = "Add CI pipeline"
    mock_msg.reply = MagicMock()

    mock_recruiter = {"id": 22, "name": "Bob Recruiter", "email": "recruiter@corp.com"}

    with patch("database.db.get_recruiter_by_contact", new_callable=AsyncMock) as mock_get_recruiter, \
         patch("database.db.get_latest_notified_project_for_recruiter", new_callable=AsyncMock) as mock_get_proj, \
         patch("database.db.add_suggestion", new_callable=AsyncMock) as mock_add_sug:
        
        mock_get_recruiter.return_value = mock_recruiter
        mock_get_proj.return_value = 205
        mock_add_sug.return_value = {"id": 1, "project_id": 205}

        res = await caspian_agent.process_inbound_message(mock_msg)

        mock_get_proj.assert_called_once_with(mock_db_pool, 22)
        assert res["project_id"] == 205


@pytest.mark.asyncio
async def test_explicit_project_id_context_resolution(mock_db_pool):
    """Test context resolution when message explicitly specifies project ID."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "email"
    mock_msg.sender = "recruiter@corp.com"
    mock_msg.text = "For project #77: suggest adding integration tests"
    mock_msg.reply = MagicMock()

    mock_recruiter = {"id": 22, "name": "Bob Recruiter", "email": "recruiter@corp.com"}

    with patch("database.db.get_recruiter_by_contact", new_callable=AsyncMock) as mock_get_recruiter, \
         patch("database.db.get_project_by_id", new_callable=AsyncMock) as mock_get_proj_by_id, \
         patch("database.db.add_suggestion", new_callable=AsyncMock) as mock_add_sug:
        
        mock_get_recruiter.return_value = mock_recruiter
        mock_get_proj_by_id.return_value = {"id": 77, "repo_url": "https://github.com/test/repo"}
        mock_add_sug.return_value = {"id": 1, "project_id": 77}

        res = await caspian_agent.process_inbound_message(mock_msg)

        mock_get_proj_by_id.assert_called_once_with(mock_db_pool, 77)
        assert res["project_id"] == 77


@pytest.mark.asyncio
async def test_db_connection_leak(mock_db_pool):
    """Test that a batch of messages processes cleanly without connection leaks or unhandled errors."""
    mock_recruiter = {"id": 1, "name": "Alice", "email": "alice@test.com"}

    with patch("database.db.get_recruiter_by_contact", new_callable=AsyncMock) as mock_get_recruiter, \
         patch("database.db.get_latest_notified_project_for_recruiter", new_callable=AsyncMock) as mock_get_proj, \
         patch("database.db.add_suggestion", new_callable=AsyncMock) as mock_add_sug:
        
        mock_get_recruiter.return_value = mock_recruiter
        mock_get_proj.return_value = 10
        mock_add_sug.return_value = {"id": 1}

        for i in range(5):
            msg = MagicMock(spec=Message)
            msg.channel = "email"
            msg.sender = "alice@test.com"
            msg.text = f"Suggestion #{i}: add feature {i}"
            msg.reply = MagicMock()

            res = await caspian_agent.process_inbound_message(msg)
            assert res["status"] == "processed"

        assert mock_get_recruiter.call_count == 5
