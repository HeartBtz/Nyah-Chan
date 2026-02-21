"""Anti-spam — rate-limit messages per user, auto-mute repeat offenders."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import timedelta
from typing import Dict, List

import discord

from .registry import register
from ..database import get_db

logger = logging.getLogger("nyahchan.feature.antispam")


class AntiSpamFeature:
    name = "antispam"

    def __init__(self) -> None:
        # user_id -> list of (timestamp, content_hash)
        self._history: Dict[int, List[float]] = defaultdict(list)

    def setup(self, client: discord.Client) -> None:
        self._client = client

    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        cfg = get_db().get_guild_config(str(message.guild.id))
        if not cfg.get("antispam_enabled"):
            return None

        member = message.author
        if isinstance(member, discord.Member) and member.guild_permissions.manage_messages:
            return None  # mods exempt

        max_msgs = int(cfg.get("antispam_max_messages", 5))
        interval = int(cfg.get("antispam_interval_seconds", 5))
        mute_min = int(cfg.get("antispam_mute_minutes", 5))

        now = time.time()
        uid = message.author.id
        history = self._history[uid]
        history.append(now)

        # Prune old entries
        cutoff = now - interval
        history[:] = [t for t in history if t > cutoff]

        if len(history) < max_msgs:
            return None

        # Spam detected
        self._history[uid] = []
        logger.info("[antispam] %s exceeded %d msgs in %ds", message.author, max_msgs, interval)

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        # Timeout the user
        if isinstance(member, discord.Member):
            me = message.guild.me
            if me and member.top_role < me.top_role:
                try:
                    until = discord.utils.utcnow() + timedelta(minutes=mute_min)
                    await member.timeout(until, reason=f"Anti-spam: {max_msgs} msgs en {interval}s")
                except Exception as e:
                    logger.error("[antispam] Timeout failed: %s", e)

        embed = discord.Embed(
            title="🔇 Anti-Spam",
            description=f"{message.author.mention}, spam détecté. Mute {mute_min} min.",
            color=discord.Color.orange(),
        )
        try:
            await message.channel.send(embed=embed, delete_after=10)
        except Exception:
            pass

        # Mod log
        from ..moderation import _log
        e = discord.Embed(
            title="🔇 Anti-Spam",
            description=f"{message.author.mention} mute {mute_min}min — {max_msgs} messages en {interval}s.",
            color=discord.Color.orange(),
        )
        await _log(message.guild, self._client, e)

        # Periodic cleanup
        if len(self._history) > 1000:
            cutoff = time.time() - 60
            self._history = {
                k: v for k, v in self._history.items() if any(t > cutoff for t in v)
            }

        return True


register(AntiSpamFeature())
