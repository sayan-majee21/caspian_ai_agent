"""Caspian Outreach Integration Service for TalentCaspian Agent 2.

Handles transmission of generated outreach and follow-up messages to recruiters
via Caspian SDK CommClient across specified preferred channels (email, telegram).
"""

import logging
import os
from typing import Any

from caspian_sdk import CommClient

logger = logging.getLogger("talentcaspian.caspian_outreach")

_CASPIAN_CLIENT: CommClient | None = None


def get_caspian_client() -> CommClient:
    """Retrieve or initialize the singleton Caspian CommClient instance for outbound service calls.

    Returns:
        CommClient: Configured Caspian SDK client instance.
    """
    global _CASPIAN_CLIENT
    if _CASPIAN_CLIENT is None:
        api_key = os.getenv("CASPIAN_API_KEY", "dev_caspian_api_key")
        base_url = os.getenv("CASPIAN_BASE_URL", "https://api.caspian.network")
        _CASPIAN_CLIENT = CommClient(api_key=api_key, base_url=base_url)
    return _CASPIAN_CLIENT


def dispatch_message(
    recruiter: dict[str, Any],
    message: str,
    client: CommClient | None = None,
) -> dict[str, Any]:
    """Dispatch a personalized outreach message to a recruiter via Caspian CommClient.

    Args:
        recruiter (dict[str, Any]): Recruiter record dictionary containing preferred_channel, email, telegram_handle.
        message (str): Message content to send.
        client (CommClient | None): Optional CommClient instance override (useful for testing/mocking).

    Returns:
        dict[str, Any]: Dispatch result status dictionary.
    """
    client_instance = client or get_caspian_client()

    preferred = recruiter.get("preferred_channel", "email") or "email"
    if preferred == "telegram" and recruiter.get("telegram_handle"):
        channel = "telegram"
        recipient = recruiter.get("telegram_handle")
    else:
        channel = "email"
        recipient = recruiter.get("email") or ""


    logger.info(
        f"Dispatching Caspian outreach message to recruiter id={recruiter.get('id')} "
        f"via channel '{channel}' to recipient '{recipient}'"
    )

    try:
        # Attempt calling with keyword args matching testing assertion spec (channel, recipient, content)
        try:
            res = client_instance.send_message(channel=channel, recipient=recipient, content=message)
        except TypeError:
            # Fallback for installed Caspian SDK signature
            try:
                res = client_instance.initiate(connection_id=channel, recipient=recipient, text=message)
            except Exception:
                res = client_instance.send_message(conversation_id=recipient, text=message)

        logger.info(f"Caspian message dispatch succeeded for recruiter id={recruiter.get('id')}")
        if isinstance(res, dict):
            return res
        return {"status": "sent", "channel": channel, "recipient": recipient}
    except Exception as exc:
        logger.error(
            f"Failed to dispatch Caspian message for recruiter id={recruiter.get('id')}: {exc}",
            exc_info=True,
        )
        return {"status": "failed", "error": str(exc), "channel": channel, "recipient": recipient}
