"""Reaction roles — add/remove roles when users react to designated messages."""
from __future__ import annotations

import logging

import discord

from ..database import get_db
from ..utils import ensure_role

logger = logging.getLogger("nyahchan.feature.reaction_roles")


class ReactionRoleMonitor:
    def __init__(self) -> None:
        self._client: discord.Client | None = None

    def setup(self, client: discord.Client) -> None:
        self._client = client

        @client.event
        async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
            await self._handle(payload, add=True)

        @client.event
        async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent) -> None:
            await self._handle(payload, add=False)

    async def _handle(self, payload: discord.RawReactionActionEvent, add: bool) -> None:
        if not payload.guild_id or payload.member and payload.member.bot:
            return
        # For reaction_remove, payload.member is None — filter bot via user_id
        if not add and payload.user_id == (self._client.user.id if self._client and self._client.user else 0):
            return

        gid = str(payload.guild_id)
        emoji_str = str(payload.emoji) if payload.emoji.id else payload.emoji.name
        db = get_db()
        rr = db.find_reaction_role(gid, str(payload.message_id), emoji_str)
        if not rr:
            return

        guild = self._client.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            try:
                member = await guild.fetch_member(payload.user_id)
            except Exception:
                return
            if not member or member.bot:
                return

        role = await ensure_role(guild, rr["role_name"])
        if not role:
            return

        me = guild.me
        if me and role.position >= me.top_role.position:
            return

        try:
            if add:
                if role not in member.roles:
                    await member.add_roles(role, reason="Reaction role")
            else:
                if role in member.roles:
                    await member.remove_roles(role, reason="Reaction role remove")
        except Exception as e:
            logger.error("[reaction_roles] %s role %s: %s",
                         "add" if add else "remove", role.name, e)


_rr_monitor = ReactionRoleMonitor()


def setup_reaction_roles(client: discord.Client) -> None:
    _rr_monitor.setup(client)
