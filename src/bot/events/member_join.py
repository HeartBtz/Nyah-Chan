"""Member join / leave events — welcome and goodbye messages + activity tracking."""
from __future__ import annotations

import logging

import discord

from ..database import get_db

logger = logging.getLogger("nyahchan.events.member")


def setup_member_events(client: discord.Client) -> None:
    @client.event
    async def on_member_join(member: discord.Member) -> None:
        # Track join activity
        try:
            get_db().increment_activity(str(member.guild.id), "joins")
        except Exception:
            pass

        cfg = get_db().get_guild_config(str(member.guild.id))
        if not cfg.get("welcome_enabled"):
            return
        channel_id = cfg.get("welcome_channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        template = cfg.get("welcome_message") or "Bienvenue {mention} ! 🎉"
        text = template.replace("{mention}", member.mention).replace(
            "{user}", str(member)
        ).replace("{server}", member.guild.name).replace(
            "{count}", str(member.guild.member_count or 0)
        )
        try:
            await channel.send(text)
        except Exception as e:
            logger.warning("Welcome send failed: %s", e)

    @client.event
    async def on_member_remove(member: discord.Member) -> None:
        # Track leave activity
        try:
            get_db().increment_activity(str(member.guild.id), "leaves")
        except Exception:
            pass

        cfg = get_db().get_guild_config(str(member.guild.id))
        if not cfg.get("goodbye_enabled"):
            return
        channel_id = cfg.get("goodbye_channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        template = cfg.get("goodbye_message") or "**{user}** a quitté **{server}**. Au revoir ! 👋"
        text = template.replace("{mention}", member.mention).replace(
            "{user}", str(member)
        ).replace("{server}", member.guild.name).replace(
            "{count}", str(member.guild.member_count or 0)
        )
        try:
            await channel.send(text)
        except Exception as e:
            logger.warning("Goodbye send failed: %s", e)
