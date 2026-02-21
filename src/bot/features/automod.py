"""Auto-moderation — bad words, mention spam, excessive CAPS.

All thresholds are per-guild and configurable via the web UI.
Returns True from on_message when a message is blocked so other features skip it.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, List

import discord

from .registry import register
from ..database import get_db
from ..utils import word_match

logger = logging.getLogger("nyahchan.feature.automod")

_MIN_CAPS_LEN = 10


class AutoModerationFeature:
    name = "automod"

    def __init__(self) -> None:
        self._violations: Dict[int, List[float]] = {}

    def setup(self, client: discord.Client) -> None:
        self._client = client

    # ---- checks ----
    @staticmethod
    def _check_bad_words(content: str, bad_words: set[str]) -> str | None:
        lower = content.lower()
        for w in bad_words:
            if word_match(w, lower):
                return w
        return None

    @staticmethod
    def _check_mentions(msg: discord.Message, max_mentions: int) -> bool:
        return (len(msg.mentions) + len(msg.role_mentions)) > max_mentions

    @staticmethod
    def _check_caps(content: str, max_pct: int) -> bool:
        alpha = [c for c in content if c.isalpha()]
        if len(alpha) < _MIN_CAPS_LEN:
            return False
        return (sum(c.isupper() for c in alpha) / len(alpha)) * 100 > max_pct

    def _record(self, uid: int) -> int:
        now = time.time()
        hist = self._violations.setdefault(uid, [])
        hist.append(now)
        cutoff = now - 600
        hist[:] = [t for t in hist if t > cutoff]
        return len(hist)

    # ---- dispatch ----
    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        cfg = get_db().get_guild_config(str(message.guild.id))
        if not cfg.get("automod_enabled"):
            return None

        member = message.author
        if isinstance(member, discord.Member) and member.guild_permissions.manage_messages:
            return None  # mods exempt

        content = message.content or ""
        reason: str | None = None

        raw_words = cfg.get("automod_bad_words", "")
        bad_words = {w.strip().lower() for w in raw_words.split(",") if w.strip()}
        if bad_words:
            hit = self._check_bad_words(content, bad_words)
            if hit:
                reason = f"Mot interdit détecté: ||{hit}||"

        if reason is None and self._check_mentions(message, int(cfg.get("automod_max_mentions", 5))):
            reason = f"Trop de mentions ({len(message.mentions) + len(message.role_mentions)})"

        if reason is None and self._check_caps(content, int(cfg.get("automod_max_caps_percent", 80))):
            reason = "Message en MAJUSCULES excessives"

        if reason is None:
            return None

        count = self._record(message.author.id)
        logger.info("[automod] #%d %s: %s", count, message.author, reason)

        try:
            await message.delete()
        except discord.Forbidden:
            return None

        embed = discord.Embed(
            title="🛡️ Auto-Modération",
            description=f"{message.author.mention}, ton message a été supprimé.",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Raison", value=reason, inline=False)
        if count >= 3:
            embed.add_field(
                name="⚠️ Attention",
                value=f"{count} violations en 10 min.",
                inline=False,
            )
        try:
            await message.channel.send(embed=embed, delete_after=15)
        except Exception:
            pass

        # Periodic memory cleanup
        if len(self._violations) > 1000:
            cutoff = time.time() - 600
            self._violations = {
                k: v for k, v in self._violations.items() if any(t > cutoff for t in v)
            }

        return True  # consumed — skip other features


register(AutoModerationFeature())
