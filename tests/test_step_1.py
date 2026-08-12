"""Unit and integration tests for Step 1 — Caspian Handshake Agent."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure root directory is on sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from caspian_sdk import CommClient, Message
import caspian_agent


def test_agent_client_initialization() -> None:
    """Verify that caspian_agent initializes a global CommClient instance."""
    assert caspian_agent.client is not None
    assert isinstance(caspian_agent.client, CommClient)


def test_single_on_message_handler_registered() -> None:
    """Verify strict eligibility gate: exactly one @client.on_message handler registered."""
    handlers = caspian_agent.client._handlers
    assert len(handlers) == 1
    assert handlers[0] == caspian_agent.unified_message_handler


def test_unified_message_handler_telegram_echo() -> None:
    """Verify unified message handler correctly processes and echoes Telegram messages."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "telegram"
    mock_msg.sender = {"id": "@testuser"}
    mock_msg.text = "Hello from Telegram!"
    mock_msg.reply = MagicMock()

    caspian_agent.unified_message_handler(mock_msg)

    mock_msg.reply.assert_called_once()
    call_kwargs = mock_msg.reply.call_args.kwargs
    assert "Echo from TalentCaspian" in call_kwargs.get("text", "")
    assert "Hello from Telegram!" in call_kwargs.get("text", "")
    assert "telegram" in call_kwargs.get("text", "")


def test_unified_message_handler_email_echo() -> None:
    """Verify unified message handler correctly processes and echoes Email messages."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "email"
    mock_msg.sender = "candidate@example.com"
    mock_msg.text = "Applying for Senior Backend Role"
    mock_msg.reply = MagicMock()

    caspian_agent.unified_message_handler(mock_msg)

    mock_msg.reply.assert_called_once()
    call_kwargs = mock_msg.reply.call_args.kwargs
    assert "Echo from TalentCaspian" in call_kwargs.get("text", "")
    assert "Applying for Senior Backend Role" in call_kwargs.get("text", "")
    assert "email" in call_kwargs.get("text", "")


def test_unified_message_handler_reply_exception_handling() -> None:
    """Verify unified message handler catches reply exceptions gracefully without crashing."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "telegram"
    mock_msg.sender = "12345"
    mock_msg.text = "Testing error path"
    mock_msg.reply.side_effect = Exception("Network timeout")

    # Should not raise exception
    caspian_agent.unified_message_handler(mock_msg)
    mock_msg.reply.assert_called_once()


def test_unified_message_handler_missing_sender_text() -> None:
    """Verify unified message handler safely handles None sender and text values."""
    mock_msg = MagicMock(spec=Message)
    mock_msg.channel = "email"
    mock_msg.sender = None
    mock_msg.text = None
    mock_msg.reply = MagicMock()

    caspian_agent.unified_message_handler(mock_msg)

    mock_msg.reply.assert_called_once()
    call_kwargs = mock_msg.reply.call_args.kwargs
    assert "Echo from TalentCaspian" in call_kwargs.get("text", "")


def test_connect_channels_with_env_vars() -> None:
    """Verify connect_channels calls client connection methods when env vars exist."""
    mock_client = MagicMock(spec=CommClient)

    with patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "mock_tg_token_12345",
            "CASPIAN_EMAIL_USER": "mock_email_user@example.com",
        },
    ):
        caspian_agent.connect_channels(mock_client)

    mock_client.connect_telegram.assert_called_once_with(bot_token="mock_tg_token_12345")
    mock_client.connect_email.assert_called_once_with(username="mock_email_user@example.com")


def test_connect_channels_handles_connection_exceptions() -> None:
    """Verify connect_channels logs exceptions during connection failure without halting."""
    mock_client = MagicMock(spec=CommClient)
    mock_client.connect_telegram.side_effect = Exception("Invalid Telegram token")
    mock_client.connect_email.side_effect = Exception("SMTP auth failed")

    with patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "bad_tg_token",
            "CASPIAN_EMAIL_USER": "bad_email_user",
        },
    ):
        caspian_agent.connect_channels(mock_client)

    mock_client.connect_telegram.assert_called_once()
    mock_client.connect_email.assert_called_once()


def test_connect_channels_without_env_vars() -> None:
    """Verify connect_channels handles missing env vars without raising exceptions."""
    mock_client = MagicMock(spec=CommClient)

    with patch.dict(os.environ, {}, clear=True):
        caspian_agent.connect_channels(mock_client)

    mock_client.connect_telegram.assert_not_called()
    mock_client.connect_email.assert_not_called()
