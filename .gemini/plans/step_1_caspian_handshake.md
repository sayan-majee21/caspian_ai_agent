# Implementation Plan: Step 1 — Caspian Handshake

## 1. Eligibility Gate Requirements
**Objective:** De-risk the core eligibility requirement of the hackathon by establishing a successful multi-channel connection using the Caspian SDK.

**Strict Single `@client.on_message` Rule:**
The hackathon strictly requires that all incoming messages, regardless of their origin channel (e.g., Email, Telegram), must be processed by a single, unified `@client.on_message` event handler.
*Why?* The core value proposition of the Caspian ecosystem is seamless multi-channel aggregation. Implementing separate handlers per channel (e.g., `@email_client.on_message` and `@telegram_client.on_message`) fundamentally bypasses the gateway's aggregation layer, violating the architectural intent of the hackathon and leading to immediate disqualification.

## 2. Setup and Dependencies

### ⚠️ Verify the import path before writing any code
The package installs as `caspian-sdk` (per `requirements.txt`), but the **top-level import name is not guaranteed to match the PyPI package name** — this is common in Python packaging (e.g. `pip install pyyaml` → `import yaml`). Before running anything below:
1. Check Caspian's official docs or `python -c "import caspian_sdk"` / `python -c "import caspian"` after install to see which resolves.
2. Update the import in `caspian_agent.py` accordingly. The script below assumes `caspian_sdk` as a placeholder — **do not treat this as confirmed**, treat it as the first thing you verify in Step 1.

### Dependencies
Ensure the Caspian SDK and related tools are installed. In your virtual environment, run:
```bash
pip install caspian-sdk python-dotenv
```
(`asyncio` is part of the Python standard library — do not add it to `pip install` or `requirements.txt`, it will fail as a package name or silently no-op.)

### Environment Configuration (`.env`)
Create a `.env` file at the root of the project with the necessary credentials:
```env
CASPIAN_API_KEY=your_caspian_api_key_here
CASPIAN_BASE_URL=https://api.caspian.network
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
CASPIAN_EMAIL_USER=your_caspian_email_address_here
```

## 3. Execution Script (`caspian_agent.py` minimal handshake script)

The agent script serves as the daemon that listens to the Caspian gateway.

### Design Principles:
- **Async Event Loop:** Must not block the main thread. Use `asyncio` to manage concurrent channel connections.
- **Unified Client:** Instantiate a single Caspian `CommClient`.
- **Channel Connections:** Dynamically attach channels (Email, Telegram) to the unified client.
- **Unified Handler:** A single `@client.on_message` that logs and echoes responses back to the original channel.

### Code Implementation (`caspian_agent.py`):

```python
import os
import asyncio
from dotenv import load_dotenv

# --- VERIFY THIS IMPORT before running (see §2 above) ---
# Try both if unsure which one the installed package exposes:
try:
    from caspian_sdk import CommClient, Message
except ImportError:
    from caspian import CommClient, Message

# Load environment variables
load_dotenv()

# Initialize the unified Caspian Client
client = CommClient(
    api_key=os.getenv("CASPIAN_API_KEY"),
    base_url=os.getenv("CASPIAN_BASE_URL")
)

@client.on_message
async def unified_message_handler(message: Message):
    """
    SINGLE UNIFIED HANDLER for all channels.
    This fulfills the strict eligibility gate requirement.
    """
    print(f"[Caspian Gateway] Received message via {message.channel} from {message.sender}")
    print(f"[Caspian Gateway] Content: {message.content}")

    # Echo response back to the originating channel
    reply_content = f"Echo from TalentCaspian: Received your message '{message.content}' via {message.channel}."

    try:
        # Note: Inspect caspian-sdk to confirm keyword parameter ('recipient' vs 'target').
        # Call with exact signature exposed by installed SDK package.
        send_kwargs = {"channel": message.channel, "content": reply_content}
        if hasattr(client.send_message, "__code__") and "recipient" in client.send_message.__code__.co_varnames:
            send_kwargs["recipient"] = message.sender
        else:
            send_kwargs["target"] = message.sender

        await client.send_message(**send_kwargs)
        print(f"[Caspian Gateway] Successfully replied to {message.sender} on {message.channel}")
    except Exception as e:
        print(f"[Caspian Gateway] Failed to send reply on {message.channel}: {e}")

async def main():
    print("Starting Caspian Handshake Agent...")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    email_user = os.getenv("CASPIAN_EMAIL_USER")

    # Connect Telegram
    if telegram_token:
        try:
            await client.connect_telegram(token=telegram_token)
            print("✓ Telegram channel connected.")
        except Exception as e:
            print(f"✗ Failed to connect Telegram: {e}")
    else:
        print("⚠ WARNING: TELEGRAM_BOT_TOKEN missing.")

    # Connect Email
    if email_user:
        try:
            await client.connect_email(user=email_user)
            print("✓ Email channel connected.")
        except Exception as e:
            print(f"✗ Failed to connect Email: {e}")
    else:
        print("⚠ WARNING: CASPIAN_EMAIL_USER missing.")

    print("Listening for messages across all connected channels...")
    # Note: Step 1 is the minimal handshake. When upgrading this file in Step 6 (Listener Agent),
    # wrap client.start_listening() with `await init_db_pool()` and `await close_db_pool()` (see Step 6).
    await client.start_listening()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAgent gracefully shutting down.")
```

## 4. Testing and Verification Protocol

### Execution Steps
1. Ensure `.env` is populated with active Caspian and channel tokens.
2. Run the agent daemon: `python caspian_agent.py`
3. Wait for the terminal to display connection confirmations for both Email and Telegram.

### Validation & Screen-Recording Checklist (For Hackathon Judges)
To prove the eligibility gate is met, record a demo following this exact sequence:
- **[ ] 1. Show Code:** Briefly display `caspian_agent.py` highlighting the single `@client.on_message` decorator to prove compliance.
- **[ ] 2. Start Agent:** Run the script in the terminal and show the "Listening..." logs.
- **[ ] 3. Test Telegram:** Send a message to the Telegram bot from a phone or separate app window.
- **[ ] 4. Test Email:** Send an email to the configured Caspian email address.
- **[ ] 5. Show Terminal Logs:** Highlight the terminal showing messages received from *both* channels passing through the exact same handler log print statements.
- **[ ] 6. Show Responses:** Show the echo replies successfully arriving back in the Telegram app and the Email inbox.

### Fail-safe Handling
- **Network Drops:** If the network drops, `asyncio` exception handling should catch `ConnectionError`. Ensure the Caspian SDK handles exponential backoff automatically, or explicitly restart the daemon.
- **Invalid Tokens:** If a token is invalid, the `connect_*` methods will raise authentication errors on startup. The `main()` loop includes `try/except` blocks during connection to prevent the entire agent from crashing if one channel fails, logging an `✗ Failed to connect` message instead.
