"""Keyword-triggered embed responses — guild-aware, DB-backed."""
from __future__ import annotations

import logging
import time
from typing import Dict

import discord

from .registry import register
from ..database import get_db
from ..utils import word_match

logger = logging.getLogger("nyahchan.feature.keyword_responses")

_NAMED_COLORS = {
    "red": discord.Color.red().value,
    "blue": discord.Color.blue().value,
    "green": discord.Color.green().value,
    "yellow": discord.Color.yellow().value,
    "purple": discord.Color.purple().value,
    "gold": discord.Color.gold().value,
    "orange": discord.Color.orange().value,
}


def _parse_color(raw: str | int) -> int:
    if isinstance(raw, int):
        return raw
    raw = str(raw).strip().lower()
    if raw in _NAMED_COLORS:
        return _NAMED_COLORS[raw]
    try:
        return int(raw.lstrip("#"), 16)
    except Exception:
        return discord.Color.default().value


class KeywordResponsesFeature:
    name = "keyword_responses"

    def __init__(self) -> None:
        self._cooldowns: Dict[str, float] = {}

    def setup(self, client: discord.Client) -> None:
        pass

    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        content = (message.content or "").lower()
        if not content:
            return None

        keywords = get_db().get_keywords(str(message.guild.id))
        if not keywords:
            return None

        now = time.time()
        # Periodic cleanup
        if len(self._cooldowns) > 500:
            cutoff = now - 60
            self._cooldowns = {k: v for k, v in self._cooldowns.items() if v > cutoff}

        channel_id = message.channel.id
        for kw in keywords:
            triggers = kw.get("triggers", [])
            for trig in triggers:
                trig_lower = trig.strip().lower()
                if not trig_lower:
                    continue
                if not word_match(trig_lower, content):
                    continue

                ck = f"{channel_id}:{trig_lower}"
                if now - self._cooldowns.get(ck, 0) < 30:
                    return None

                color = _parse_color(kw.get("color", ""))
                embed = discord.Embed(
                    title=kw.get("title", ""),
                    description=kw.get("description", ""),
                    color=color,
                )
                for f in kw.get("fields", []):
                    embed.add_field(
                        name=f.get("name", ""),
                        value=f.get("value", ""),
                        inline=f.get("inline", False),
                    )
                if kw.get("footer"):
                    embed.set_footer(text=kw["footer"])
                if kw.get("image_url"):
                    embed.set_image(url=kw["image_url"])
                if kw.get("thumbnail_url"):
                    embed.set_thumbnail(url=kw["thumbnail_url"])

                try:
                    await message.channel.send(embed=embed)
                    self._cooldowns[ck] = now
                except Exception as e:
                    logger.warning("Keyword embed send failed: %s", e)
                return None  # one match per message

        return None


register(KeywordResponsesFeature())
