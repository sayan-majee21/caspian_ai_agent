"""
TalentCaspian - Caspian Handshake Agent Daemon.

This script initializes the Caspian CommClient, connects multi-channel interfaces
(Telegram, Email), and registers a single unified message handler to aggregate
and process incoming messages across all connected channels.
"""

import os
import sys
import logging
import asyncio
from typing import Optional
from dotenv import load_dotenv
from caspian_sdk import CommClient, Message

# Setup logger for Caspian agent daemon
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TalentCaspian.Agent")

# Load environment configuration
load_dotenv()

# Initialize the single unified Caspian CommClient
client: CommClient = CommClient(
    api_key=os.getenv("CASPIAN_API_KEY") or "dev_caspian_api_key",
    base_url=os.getenv("CASPIAN_BASE_URL", "https://api.caspian.network")
)


@client.on_message
async def unified_message_handler(message: Message) -> None:
    """
    SINGLE UNIFIED HANDLER for all incoming channel messages.
    
    This handler fulfills the strict eligibility gate requirement for the
    Caspian ecosystem hackathon by processing messages from all connected
    channels (Email, Telegram, etc.) through a single event handler.

    Args:
        message (Message): Inbound message object from Caspian SDK.
    """
    sender_info = message.sender.get("id") if isinstance(message.sender, dict) else str(message.sender)
    msg_text = message.text or ""

    logger.info(
        "[Caspian Gateway] Received message via channel '%s' from '%s'",
        message.channel,
        sender_info
    )
    logger.info("[Caspian Gateway] Content: '%s'", msg_text)

    # Prepare echo response
    reply_content: str = (
        f"Echo from TalentCaspian: Received your message '{msg_text}' via {message.channel}."
    )

    try:
        message.reply(text=reply_content)
        logger.info(
            "[Caspian Gateway] Successfully replied to '%s' on channel '%s'",
            sender_info,
            message.channel
        )
    except Exception as exc:
        logger.error(
            "[Caspian Gateway] Failed to send reply on channel '%s': %s",
            message.channel,
            exc
        )


def connect_channels(comm_client: CommClient) -> None:
    """
    Connect multi-channel endpoints (Telegram, Email) to the Caspian client.

    Args:
        comm_client (CommClient): The instantiated Caspian client.
    """
    telegram_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    email_user: Optional[str] = os.getenv("CASPIAN_EMAIL_USER")

    # Connect Telegram
    if telegram_token:
        try:
            comm_client.connect_telegram(bot_token=telegram_token)
            logger.info("✓ Telegram channel connected successfully.")
        except Exception as exc:
            logger.error("✗ Failed to connect Telegram channel: %s", exc)
    else:
        logger.warning("⚠ TELEGRAM_BOT_TOKEN missing in environment configuration.")

    # Connect Email
    if email_user:
        try:
            comm_client.connect_email(username=email_user)
            logger.info("✓ Email channel connected successfully for user '%s'.", email_user)
        except Exception as exc:
            logger.error("✗ Failed to connect Email channel: %s", exc)
    else:
        logger.warning("⚠ CASPIAN_EMAIL_USER missing in environment configuration.")


def run_listener(comm_client: CommClient) -> None:
    """
    Start the blocking event listener loop for the Caspian client.
    
    Can be run directly or inside a worker thread to prevent blocking
    the main event loop.

    Args:
        comm_client (CommClient): The instantiated Caspian client.
    """
    logger.info("Listening for incoming messages across all connected channels...")
    comm_client.listen()


async def main() -> None:
    """Main async entry point for starting the Caspian Handshake Agent."""
    logger.info("Starting Caspian Handshake Agent Daemon...")
    
    connect_channels(client)

    # Run the blocking listener loop in a thread pool to preserve async responsiveness
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_listener, client)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nCaspian Handshake Agent gracefully shut down by user.")
    except Exception as main_exc:
        logger.critical("Fatal error running Caspian Handshake Agent: %s", main_exc)
        sys.exit(1)
