from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from importlib import util as importlib_util

import discord
from dotenv import find_dotenv, load_dotenv

from .features import commands  # noqa: F401
from .features import grant_commands  # noqa: F401
from .features import keyword_responses  # noqa: F401
from .features import ollama_qna  # noqa: F401
from .features import role_triggers  # noqa: F401
from .features import registry as feature_registry
from .moderation import ModerationCommands

logger = logging.getLogger("nyahchan")

# Global bot state (accessible from web panel)
bot_state = {
    "started_at": None,
    "guilds": 0,
    "users": 0,
    "client": None,
    "ready": False,
}


def create_client() -> discord.Client:
    """Create the Discord client with appropriate intents."""
    intents = discord.Intents.default()
    intents.message_content = True
    use_members = os.getenv("USE_MEMBERS_INTENT", "1") not in ("0", "false", "False")
    if use_members:
        intents.members = True
    client = discord.Client(intents=intents)
    return client


def setup_logging() -> None:
    """Configure logging with console and file output.

    LOG_LEVEL (.env) can be DEBUG, INFO, WARNING, ERROR, CRITICAL.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)

    # File handler (rotating would be better, but keep it simple)
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler("logs/nyahchan.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Reduce noise from libraries
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def preflight_checks() -> bool:
    """Run checks before launching the client."""
    if importlib_util.find_spec("audioop") is None:
        logger.warning(
            "Module 'audioop' absent (removed in Python 3.13). "
            "Audio features won't work. Install 'audioop-lts' or use Python ≤3.12."
        )

    token = os.getenv("DISCORD_TOKEN", "")
    if not token or token in ("YOUR_TOKEN", "YOUR_TOKEN_HERE"):
        logger.error("DISCORD_TOKEN is missing or invalid. Set it in .env")
        return False

    return True


async def async_main() -> None:
    """Main async entry point for the bot."""
    load_dotenv(find_dotenv())
    setup_logging()

    if not preflight_checks():
        return

    token = os.getenv("DISCORD_TOKEN", "")
    client = create_client()

    # Store client reference globally
    bot_state["client"] = client
    bot_state["started_at"] = datetime.now(timezone.utc).isoformat()

    # Moderation slash commands
    moderation = ModerationCommands(client)
    setattr(client, "moderation", moderation)

    # Features (imported above to trigger registry)
    from .features.registry import reload_all, setup_all
    from .web import set_bot_state, set_reload_callback

    # Import and setup events
    from .events.member_join import setup_member_join_event
    from .events.message_create import setup_message_event
    from .events.ready import setup_ready_event

    setup_ready_event(client)
    setup_message_event(client)
    setup_member_join_event(client)
    setup_all(client)

    # Allow the web UI to trigger a hot-reload
    def _reload_features() -> None:
        logger.info("Hot-reload of features requested via WebGUI")
        reload_all()

    set_reload_callback(_reload_features)
    set_bot_state(bot_state)

    # Graceful shutdown handler
    async def _shutdown() -> None:
        logger.info("Shutting down gracefully...")
        await client.close()

    try:
        await client.start(token)
    except discord.errors.PrivilegedIntentsRequired:
        logger.error(
            "Privileged intents are missing. Enable them in the Discord Developer Portal:\n"
            "  Application -> Bot -> Privileged Gateway Intents:\n"
            "  - Server Members Intent (if USE_MEMBERS_INTENT=1)\n"
            "  - Message Content Intent (required)\n"
            "Or set USE_MEMBERS_INTENT=0 to disable Members intent."
        )
    except discord.errors.LoginFailure:
        logger.error("Invalid Discord token. Check DISCORD_TOKEN in .env")
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
    finally:
        bot_state["ready"] = False
        if not client.is_closed():
            await client.close()


def main() -> None:
    """Synchronous entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")


if __name__ == "__main__":
    main()
