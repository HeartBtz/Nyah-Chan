from __future__ import annotations

import logging

import discord

logger = logging.getLogger("nyahchan.events.ready")

_synced = False  # Only sync slash commands once per process lifetime


def setup_ready_event(client: discord.Client) -> None:
    @client.event
    async def on_ready() -> None:
        global _synced
        assert client.user is not None
        logger.info(
            "Connected as %s (%s) | Guilds: %d | Users: %d",
            client.user, client.user.id,
            len(client.guilds),
            sum(g.member_count or 0 for g in client.guilds),
        )

        # Update global bot state
        from ..main import bot_state
        bot_state["ready"] = True
        bot_state["guilds"] = len(client.guilds)
        bot_state["users"] = sum(g.member_count or 0 for g in client.guilds)

        # Set bot presence
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(client.guilds)} serveur(s) | !help",
        )
        await client.change_presence(status=discord.Status.online, activity=activity)

        # Sync slash commands (once per session to avoid rate limits)
        if not _synced:
            moderation = getattr(client, "moderation", None)
            if moderation is not None:
                try:
                    await moderation.sync()
                    _synced = True
                except Exception as e:
                    logger.error("Failed to sync slash commands: %s", e)
