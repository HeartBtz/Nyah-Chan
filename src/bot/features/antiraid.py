"""Anti-raid — detect mass joins and take action."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Dict, List

import discord

from ..database import get_db

logger = logging.getLogger("nyahchan.feature.antiraid")


class AntiRaidMonitor:
    """Monitors member joins per guild and triggers action when threshold is exceeded."""

    def __init__(self) -> None:
        # guild_id -> list of join timestamps
        self._joins: Dict[int, List[float]] = defaultdict(list)
        self._lockdown_until: Dict[int, float] = {}

    def setup(self, client: discord.Client) -> None:
        self._client = client

        @client.event
        async def on_member_join(member: discord.Member) -> None:
            # Call original handler first (welcome messages)
            # This is handled in events/member_join.py; we just monitor
            await self._check_raid(member)

    async def _check_raid(self, member: discord.Member) -> None:
        guild = member.guild
        gid = str(guild.id)
        cfg = get_db().get_guild_config(gid)
        if not cfg.get("antiraid_enabled"):
            return

        now = time.time()
        max_joins = int(cfg.get("antiraid_join_count", 10))
        window = int(cfg.get("antiraid_join_seconds", 30))
        action = cfg.get("antiraid_action", "kick")

        # Record join
        joins = self._joins[guild.id]
        joins.append(now)
        cutoff = now - window
        joins[:] = [t for t in joins if t > cutoff]

        if len(joins) < max_joins:
            return

        # RAID detected
        logger.warning("[antiraid] Raid detected on %s (%d joins in %ds)",
                       guild.name, len(joins), window)

        # Clear to avoid repeated triggers
        self._joins[guild.id] = []

        me = guild.me
        if me is None:
            return

        # Get recent members (joined in last `window` seconds)
        recent_members = [
            m for m in guild.members
            if m.joined_at and (now - m.joined_at.timestamp()) < window * 2
            and not m.bot and m != me
        ]

        actioned = 0
        for m in recent_members:
            if m.top_role >= me.top_role:
                continue
            try:
                if action == "ban":
                    await guild.ban(m, reason=f"Anti-raid: {len(joins)} joins en {window}s")
                    actioned += 1
                elif action == "kick":
                    await guild.kick(m, reason=f"Anti-raid: {len(joins)} joins en {window}s")
                    actioned += 1
            except Exception as e:
                logger.error("[antiraid] Failed to %s %s: %s", action, m, e)

        # Send mod log
        from ..moderation import _log
        e = discord.Embed(
            title="🚨 Raid détecté !",
            description=f"**{len(joins)}** joins en **{window}s** — {actioned} membre(s) {action}.",
            color=discord.Color.dark_red(),
        )
        await _log(guild, self._client, e)


_antiraid = AntiRaidMonitor()


def setup_antiraid(client: discord.Client) -> None:
    _antiraid.setup(client)


def get_antiraid() -> AntiRaidMonitor:
    return _antiraid
