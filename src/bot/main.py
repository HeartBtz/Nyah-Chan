"""Nyah-Chan — Discord bot entry point."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

import discord
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger("nyahchan")

# Global bot state (read by web panel)
bot_state: dict = {
    "started_at": None,
    "guilds": 0,
    "users": 0,
    "client": None,
    "ready": False,
}


# ------------------------------------------------------------------
# Client
# ------------------------------------------------------------------
def create_client() -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True
    if os.getenv("USE_MEMBERS_INTENT", "1") not in ("0", "false"):
        intents.members = True
    return discord.Client(intents=intents)


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    os.makedirs("logs", exist_ok=True)
    fh = RotatingFileHandler(
        "logs/nyahchan.log", encoding="utf-8",
        maxBytes=5 * 1024 * 1024, backupCount=3,
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(fh)

    for noisy in ("discord.gateway", "discord.http", "discord.client",
                   "uvicorn.access", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ------------------------------------------------------------------
# Async main
# ------------------------------------------------------------------
async def async_main() -> None:
    load_dotenv(find_dotenv())
    setup_logging()

    token = os.getenv("DISCORD_TOKEN", "")
    if not token or token in ("YOUR_TOKEN", "YOUR_TOKEN_HERE"):
        logger.error("DISCORD_TOKEN missing or invalid. Set it in .env")
        return

    # Initialise the database (must be before feature imports)
    from .database import init_db
    init_db(os.getenv("DATABASE_PATH", "nyahchan.db"))

    client = create_client()
    bot_state["client"] = client
    bot_state["started_at"] = datetime.now(timezone.utc).isoformat()

    # Moderation slash commands
    from .moderation import ModerationCommands
    moderation = ModerationCommands(client)
    setattr(client, "moderation", moderation)

    # Feature imports (trigger registry.register calls)
    from .features import automod  # noqa: F401
    from .features import commands  # noqa: F401
    from .features import grant_commands  # noqa: F401
    from .features import keyword_responses  # noqa: F401
    from .features import ollama_qna  # noqa: F401
    from .features import role_triggers  # noqa: F401
    from .features.registry import setup_all
    from .events.ready import setup_ready_event
    from .events.message_create import setup_message_event
    from .events.member_join import setup_member_events

    setup_ready_event(client)
    setup_message_event(client)
    setup_member_events(client)
    setup_all(client)

    # Web panel callbacks
    from .web import set_bot_state
    set_bot_state(bot_state)

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(client.close()))
        except NotImplementedError:
            pass

    try:
        await client.start(token)
    except discord.errors.PrivilegedIntentsRequired:
        logger.error(
            "Privileged intents missing. Enable them in the Developer Portal:\n"
            "  Server Members Intent + Message Content Intent"
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
        pass
