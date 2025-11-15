#!/usr/bin/env python3
"""Lance à la fois le bot Discord et l'interface web d'administration.

- Bot : comportement identique à run_bot.py
- Web : disponible sur http://127.0.0.1:8000 (FastAPI)
"""

from __future__ import annotations

import asyncio
import os

from src.bot.main import async_main  # type: ignore
from src.bot.web import start_web_app  # type: ignore


async def main() -> None:
    # Lancer bot + web en parallèle
    bot_task = asyncio.create_task(async_main())

    # Host/port configurables via env si besoin
    host = os.getenv("NYAH_WEB_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("NYAH_WEB_PORT", "8000"))
    except ValueError:
        port = 8000

    web_task = asyncio.create_task(start_web_app(host=host, port=port))

    # Attendre que l'un des deux termine (en pratique, Ctrl+C stoppera tout)
    await asyncio.gather(bot_task, web_task)


if __name__ == "__main__":  # pragma: no cover
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
