"""on_ready event — update bot state, set presence, sync slash commands."""
from __future__ import annotations

import logging

import discord

logger = logging.getLogger("nyahchan.events.ready")

_synced = False


def setup_ready_event(client: discord.Client) -> None:
    @client.event
    async def on_ready() -> None:
        global _synced
        from ..main import bot_state

        bot_state["guilds"] = len(client.guilds)
        bot_state["users"] = sum(g.member_count or 0 for g in client.guilds)
        bot_state["ready"] = True

        logger.info(
            "Logged in as %s (ID %s) | %d guild(s), ~%d users",
            client.user,
            client.user.id if client.user else "?",
            bot_state["guilds"],
            bot_state["users"],
        )

        await client.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{bot_state['guilds']} server(s) 🐾",
            )
        )

        if not _synced:
            mod = getattr(client, "moderation", None)
            if mod:
                await mod.sync()
                _synced = True
