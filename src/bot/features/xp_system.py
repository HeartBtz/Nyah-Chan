"""XP / Levels system — earn XP by chatting, level up, role rewards."""
from __future__ import annotations

import logging
import random
import time
from typing import Dict

import discord

from .registry import register
from ..database import get_db
from ..utils import ensure_role

logger = logging.getLogger("nyahchan.feature.xp")


class XPFeature:
    name = "xp_system"

    def __init__(self) -> None:
        # user_id -> last XP gain timestamp
        self._cooldowns: Dict[int, float] = {}

    def setup(self, client: discord.Client) -> None:
        self._client = client

    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        gid = str(message.guild.id)
        cfg = get_db().get_guild_config(gid)
        if not cfg.get("xp_enabled"):
            return None

        uid = message.author.id
        now = time.time()
        cooldown = int(cfg.get("xp_cooldown_seconds", 60))

        if now - self._cooldowns.get(uid, 0) < cooldown:
            return None

        self._cooldowns[uid] = now

        xp_min = int(cfg.get("xp_min", 15))
        xp_max = int(cfg.get("xp_max", 25))
        amount = random.randint(xp_min, xp_max)

        db = get_db()
        result = db.add_xp(gid, str(uid), amount)

        # Level up?
        if result["level"] > result["old_level"]:
            new_level = result["level"]
            await self._announce_level_up(message, cfg, new_level)
            await self._grant_level_rewards(message.guild, message.author, gid, new_level)

        # Periodic cleanup
        if len(self._cooldowns) > 2000:
            cutoff = now - cooldown * 2
            self._cooldowns = {k: v for k, v in self._cooldowns.items() if v > cutoff}

        return None

    async def _announce_level_up(self, message: discord.Message, cfg: dict, level: int) -> None:
        template = cfg.get("xp_level_up_message") or "🎉 {mention} est passé au niveau **{level}** !"
        text = template.replace("{mention}", message.author.mention).replace(
            "{level}", str(level)
        ).replace("{user}", str(message.author))

        # Determine channel
        ch_id = cfg.get("xp_level_up_channel_id")
        channel = None
        if ch_id:
            try:
                channel = message.guild.get_channel(int(ch_id))
            except (ValueError, TypeError):
                pass
        if channel is None:
            channel = message.channel

        embed = discord.Embed(
            title="⬆️ Level Up !",
            description=text,
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.warning("[xp] Level up announce failed: %s", e)

    async def _grant_level_rewards(self, guild: discord.Guild, user: discord.abc.User,
                                   guild_id: str, level: int) -> None:
        rewards = get_db().get_xp_role_rewards(guild_id)
        for r in rewards:
            if r["level"] <= level:
                role = await ensure_role(guild, r["role_name"])
                if role and isinstance(user, discord.Member) and role not in user.roles:
                    try:
                        await user.add_roles(role, reason=f"XP level {level} reward")
                    except Exception as e:
                        logger.error("[xp] grant reward role %s failed: %s", r["role_name"], e)


register(XPFeature())
