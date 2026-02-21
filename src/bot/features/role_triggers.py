"""Role triggers — add/remove roles based on message content, DB-backed."""
from __future__ import annotations

import logging

import discord

from .registry import register
from ..database import get_db
from ..utils import ensure_role, word_match

logger = logging.getLogger("nyahchan.feature.roles")


class RoleTriggersFeature:
    name = "role_triggers"

    def setup(self, client: discord.Client) -> None:
        pass

    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        guild = message.guild
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return None

        cfg = get_db().get_guild_config(str(guild.id))
        reactions_on = cfg.get("reactions_enabled", 1)

        triggers = get_db().get_role_triggers(str(guild.id))
        if not triggers:
            return None

        content = (message.content or "").lower()

        for rt in triggers:
            tw = (rt.get("trigger_word") or "").lower()
            rw = (rt.get("remove_trigger") or "").lower() or None

            trigger_hit = word_match(tw, content) if tw else False
            remove_hit = word_match(rw, content) if rw else False

            if not trigger_hit and not remove_hit:
                continue

            role = await ensure_role(guild, rt.get("role_name", ""))
            if role is None:
                continue
            if role.position >= me.top_role.position:
                continue

            member = message.author if isinstance(message.author, discord.Member) else None
            if member is None:
                try:
                    member = await guild.fetch_member(message.author.id)
                except Exception:
                    continue

            if trigger_hit and not remove_hit:
                if role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Trigger '{tw}'")
                        if reactions_on:
                            await message.add_reaction("✅")
                    except Exception as e:
                        logger.error("add_roles %s: %s", role.name, e)

            if remove_hit:
                if role in member.roles:
                    try:
                        await member.remove_roles(role, reason=f"Remove trigger '{rw}'")
                        if reactions_on:
                            await message.add_reaction("🗑️")
                    except Exception as e:
                        logger.error("remove_roles %s: %s", role.name, e)

        return None


register(RoleTriggersFeature())
