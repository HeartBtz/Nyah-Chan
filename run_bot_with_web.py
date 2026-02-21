#!/usr/bin/env python3
"""Lance à la fois le bot Discord et l'interface web d'administration.

- Bot : comportement identique à run_bot.py
- Web : disponible sur http://0.0.0.0:8000 (FastAPI)
"""

from __future__ import annotations

import asyncio
import os
import signal

from dotenv import load_dotenv

# Load .env BEFORE importing bot code so all env vars are available
load_dotenv()

from src.bot.main import async_main  # type: ignore  # noqa: E402
from src.bot.web import start_web_app  # type: ignore  # noqa: E402


async def main() -> None:
    host = os.getenv("NYAH_WEB_HOST", "0.0.0.0")
    try:
        port = int(os.getenv("NYAH_WEB_PORT", "8000"))
    except ValueError:
        port = 8000

    bot_task = asyncio.create_task(async_main(), name="discord-bot")
    web_task = asyncio.create_task(start_web_app(host=host, port=port), name="web-panel")

    # Graceful shutdown on SIGTERM/SIGINT
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: [t.cancel() for t in (bot_task, web_task)])
        except NotImplementedError:
            pass  # Windows

    try:
        await asyncio.gather(bot_task, web_task)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":  # pragma: no cover
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
