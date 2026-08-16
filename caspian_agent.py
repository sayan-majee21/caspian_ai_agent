"""TalentCaspian - Caspian Listener Agent Daemon (Reply Handling).

This daemon processes incoming replies from recruiters across all connected Caspian channels
(Email, Telegram), resolves recruiter identity and project context, parses intent via Gemini Flash
(or regex fallback), and updates project suggestions and ratings in PostgreSQL.
"""

import asyncio
import logging
import os
import re
import sys
from typing import Any, Optional

from dotenv import load_dotenv

from caspian_sdk import CommClient, Message
import database.db as db
from services.reply_parser import parse_recruiter_reply

# Setup logger for Caspian agent daemon
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("TalentCaspian.Agent")

# Load environment configuration
load_dotenv()

api_key = os.getenv("CASPIAN_API_KEY")
if not api_key:
    logger.warning("⚠ CASPIAN_API_KEY missing in environment configuration; using dev key.")
    api_key = "dev_caspian_api_key"

# Initialize the single unified Caspian CommClient
client: CommClient = CommClient(
    api_key=api_key,
    base_url=os.getenv("CASPIAN_BASE_URL", "https://api.caspian.network"),
)

# Reference to the main asyncio event loop (where DB pool is initialized)
MAIN_EVENT_LOOP: Optional[asyncio.AbstractEventLoop] = None


def run_sync_coro(coro: Any) -> Any:
    """Execute an async coroutine synchronously safely across thread and loop contexts."""
    global MAIN_EVENT_LOOP

    if MAIN_EVENT_LOOP is not None and MAIN_EVENT_LOOP.is_running():
        try:
            current_loop = None
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if current_loop is MAIN_EVENT_LOOP:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(lambda: asyncio.run(coro)).result()
            else:
                fut = asyncio.run_coroutine_threadsafe(coro, MAIN_EVENT_LOOP)
                return fut.result(timeout=15)
        except Exception as exc:
            logger.error("Error scheduling coroutine on MAIN_EVENT_LOOP: %s", exc)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
    else:
        return asyncio.run(coro)


async def process_inbound_message(message: Message) -> dict[str, Any]:
    """Process an inbound recruiter reply message.

    Extracts sender info, resolves recruiter identity and project context from DB,
    parses intent using Gemini/regex, and executes database mutations.

    Args:
        message (Message): Inbound message object from Caspian SDK.

    Returns:
        dict[str, Any]: Status and result summary of message processing.
    """
    if isinstance(message.sender, dict):
        sender_info = (
            message.sender.get("email")
            or message.sender.get("id")
            or message.sender.get("handle")
            or ""
        )
    else:
        sender_info = (
            getattr(message.sender, "email", None)
            or getattr(message.sender, "handle", None)
            or getattr(message.sender, "id", None)
            or str(message.sender or "")
        )
    msg_text = message.text or ""
    channel = getattr(message, "channel", "email") or "email"

    logger.info(
        "[Caspian Gateway] Processing inbound message via channel '%s' from '%s'",
        channel,
        sender_info,
    )

    # Fallback echo response if DB pool is uninitialized
    if not db.is_pool_ready():
        logger.warning("Database pool is not ready; executing fallback echo reply.")
        reply_text = f"Echo from TalentCaspian: Received your message '{msg_text}' via {channel}."
        try:
            message.reply(text=reply_text)
        except Exception as exc:
            logger.error("[Caspian Gateway] Fallback reply failed: %s", exc)
        return {"status": "db_not_ready", "reply": reply_text}

    # Step 1: Recruiter Identity Resolution
    recruiter = await db.get_recruiter_by_contact(db.DB_POOL, sender_info)
    if not recruiter:
        logger.warning("[Caspian Gateway] Unrecognized sender: '%s'", sender_info)
        reply_text = (
            f"Echo from TalentCaspian: Received your message '{msg_text}' via {channel}. "
            "Note: Sender not recognized in recruiter database."
        )
        try:
            message.reply(text=reply_text)
        except Exception as exc:
            logger.error("[Caspian Gateway] Unrecognized sender reply failed: %s", exc)
        return {"status": "unrecognized_sender", "sender": sender_info}

    recruiter_id = recruiter["id"]

    # Step 2: Context Mapping (Project Resolution)
    # Check for explicit project ID pattern in text (e.g. project_id: 1 or proj #1 or [project: 1])
    explicit_proj_match = re.search(r"\b(?:project|proj)[ _#:]*(\d+)\b", msg_text, re.IGNORECASE)
    project_id: Optional[int] = None
    if explicit_proj_match:
        try:
            pid = int(explicit_proj_match.group(1))
            proj = await db.get_project_by_id(db.DB_POOL, pid)
            if proj:
                project_id = pid
        except Exception:
            pass

    if project_id is None:
        project_id = await db.get_latest_notified_project_for_recruiter(db.DB_POOL, recruiter_id)

    if project_id is None:
        logger.warning("[Caspian Gateway] No project context found for recruiter ID %s", recruiter_id)
        reply_text = (
            f"Echo from TalentCaspian: Received your message '{msg_text}' via {channel}. "
            f"No project notification history found for {recruiter['name']}."
        )
        try:
            message.reply(text=reply_text)
        except Exception as exc:
            logger.error("[Caspian Gateway] No project context reply failed: %s", exc)
        return {"status": "no_project_context", "recruiter_id": recruiter_id}

    # Step 3: Intent Classification
    parsed = await parse_recruiter_reply(msg_text)
    intent = parsed.get("intent", "noise")
    sug_text = parsed.get("suggestion_text")
    rating_val = parsed.get("rating")

    suggestion_added = False
    rating_added = False

    # Step 4: Database Mutations
    if sug_text:
        await db.add_suggestion(
            db.DB_POOL,
            {
                "project_id": project_id,
                "recruiter_id": recruiter_id,
                "suggestion_text": sug_text,
            },
        )
        suggestion_added = True
        logger.info(
            "[Caspian Listener] Added unresolved suggestion for project #%s from recruiter #%s: '%s'",
            project_id,
            recruiter_id,
            sug_text,
        )

    if rating_val is not None:
        await db.add_project_rating(
            db.DB_POOL,
            {
                "project_id": project_id,
                "rater_type": "recruiter",
                "rater_id": recruiter_id,
                "rating": rating_val,
            },
        )
        new_score = await db.update_project_score(db.DB_POOL, project_id)
        rating_added = True
        logger.info(
            "[Caspian Listener] Added recruiter rating %s/10 for project #%s (New Score: %s)",
            rating_val,
            project_id,
            new_score,
        )

    # Step 5: Craft Feedback Reply
    if suggestion_added and rating_added:
        reply_content = (
            f"Thank you {recruiter['name']}! We recorded your rating of {rating_val}/10 and "
            f"suggestion: '{sug_text}' for project #{project_id}."
        )
    elif suggestion_added:
        reply_content = (
            f"Thank you {recruiter['name']}! We recorded your suggestion for project #{project_id}: '{sug_text}'."
        )
    elif rating_added:
        reply_content = (
            f"Thank you {recruiter['name']}! We recorded your rating of {rating_val}/10 for project #{project_id}."
        )
    else:
        reply_content = f"Echo from TalentCaspian: Received your message '{msg_text}' via {channel}."

    try:
        message.reply(text=reply_content)
        logger.info("[Caspian Gateway] Sent reply to recruiter '%s': %s", recruiter['name'], reply_content)
    except Exception as exc:
        logger.error("[Caspian Gateway] Failed to send reply: %s", exc)

    return {
        "status": "processed",
        "recruiter_id": recruiter_id,
        "project_id": project_id,
        "intent": intent,
        "suggestion_added": suggestion_added,
        "rating_added": rating_added,
        "parsed": parsed,
    }


@client.on_message
def unified_message_handler(message: Message) -> None:
    """SINGLE UNIFIED HANDLER for all incoming channel messages.

    Fulfills strict eligibility gate requirement by processing messages
    from all connected channels (Email, Telegram, etc.) through a single event handler.

    Args:
        message (Message): Inbound message object from Caspian SDK.
    """
    try:
        run_sync_coro(process_inbound_message(message))
    except Exception as exc:
        logger.error("[Caspian Gateway] Error in unified_message_handler: %s", exc, exc_info=True)


def connect_channels(comm_client: CommClient) -> None:
    """Connect multi-channel endpoints (Telegram, Email) to the Caspian client.

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
            logger.error("✗ Failed to connect Telegram channel: %s", exc, exc_info=True)
    else:
        logger.warning("⚠ TELEGRAM_BOT_TOKEN missing in environment configuration.")

    # Connect Email
    if email_user:
        try:
            comm_client.connect_email(username=email_user)
            logger.info("✓ Email channel connected successfully for user '%s'.", email_user)
        except Exception as exc:
            logger.error("✗ Failed to connect Email channel: %s", exc, exc_info=True)
    else:
        logger.warning("⚠ CASPIAN_EMAIL_USER missing in environment configuration.")


def run_listener(comm_client: CommClient) -> None:
    """Start the event listener loop for the Caspian client with reconnection resilience.

    Args:
        comm_client (CommClient): The instantiated Caspian client.
    """
    logger.info("Listening for incoming messages across all connected channels...")
    retry_delay = 2
    while True:
        try:
            comm_client.listen()
            break
        except Exception as exc:
            logger.error(
                "Caspian listener loop encountered error: %s. Reconnecting in %ss...",
                exc,
                retry_delay,
            )
            import time
            time.sleep(retry_delay)
            retry_delay = min(30, retry_delay * 2)


async def main() -> None:
    """Main async entry point for starting the Caspian Listener Agent."""
    global MAIN_EVENT_LOOP
    logger.info("Starting Caspian Listener Agent Daemon...")
    try:
        MAIN_EVENT_LOOP = asyncio.get_running_loop()
        await db.init_db_pool()
        connect_channels(client)

        # Run the blocking listener loop in a thread pool executor to preserve async responsiveness
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, run_listener, client)
    finally:
        await db.close_db_pool()
        client.close()
        MAIN_EVENT_LOOP = None


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nCaspian Listener Agent gracefully shut down by user.")
    except Exception as main_exc:
        logger.critical("Fatal error running Caspian Listener Agent: %s", main_exc)
        sys.exit(1)
