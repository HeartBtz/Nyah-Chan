"""Ollama Q&A — mention the bot with a question, DB-backed config."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict

import aiohttp
import discord

from .registry import register
from ..database import get_db

logger = logging.getLogger("nyahchan.feature.ollama")


class OllamaQnAFeature:
    name = "ollama_qna"

    def __init__(self) -> None:
        self._rate: Dict[str, float] = {}
        self._session: aiohttp.ClientSession | None = None
        self._max_chunk = 1900

    def setup(self, client: discord.Client) -> None:
        self._client = client

    async def _get_session(self, timeout: int) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            )
        return self._session

    async def _query(self, base_url: str, model: str, prompt: str,
                     system: str | None, timeout: int) -> str:
        url = f"{base_url.rstrip('/')}/api/generate"
        payload: dict = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        try:
            sess = await self._get_session(timeout)
            async with sess.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return f"Erreur Ollama ({resp.status}): {text[:500]}"
                data = await resp.json()
                return str(data.get("response", "(Réponse vide)")).strip()
        except asyncio.TimeoutError:
            return "(Timeout Ollama)"
        except Exception as e:
            logger.error("[ollama] %s", e)
            return f"(Erreur: {e})"

    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        cfg = get_db().get_guild_config(str(message.guild.id))
        if not cfg.get("ollama_enabled"):
            return None

        bot_user = message.guild.me
        if bot_user is None or bot_user not in message.mentions:
            return None

        content = (message.content or "").replace(f"<@{bot_user.id}>", "").replace(f"<@!{bot_user.id}>", "").strip()
        if not content or "?" not in content:
            return None

        # Rate limit
        now = time.time()
        uk = str(message.author.id)
        if now - self._rate.get(uk, 0) < 15:
            rem = int(15 - (now - self._rate.get(uk, 0)))
            await message.channel.send(f"⏳ Patiente {rem}s.", delete_after=5)
            return None
        self._rate[uk] = now

        # Cleanup
        if len(self._rate) > 500:
            cutoff = now - 30
            self._rate = {k: v for k, v in self._rate.items() if v > cutoff}

        base_url = cfg.get("ollama_base_url", "http://localhost:11434")
        model = cfg.get("ollama_model", "llama3")
        timeout = int(cfg.get("ollama_timeout", 60))
        system = cfg.get("ollama_system_prompt") or None

        async with message.channel.typing():
            answer = await self._query(base_url, model, content, system, timeout)

        if len(answer) <= 4000:
            embed = discord.Embed(description=answer, color=discord.Color.blurple())
            embed.set_author(
                name=f"Réponse pour {message.author.display_name}",
                icon_url=message.author.display_avatar.url if message.author.display_avatar else None,
            )
            embed.set_footer(text=f"Modèle: {model}")
            await message.reply(embed=embed, mention_author=False)
        else:
            chunks = [answer[i:i + self._max_chunk] for i in range(0, len(answer), self._max_chunk)]
            for idx, ch in enumerate(chunks, 1):
                header = f"(part {idx}/{len(chunks)})\n" if len(chunks) > 1 else ""
                await message.channel.send(header + ch)

        return None


register(OllamaQnAFeature())
