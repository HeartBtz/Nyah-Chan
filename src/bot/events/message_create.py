"""on_message event — dispatch to feature registry + track activity."""
from __future__ import annotations

import discord


def setup_message_event(client: discord.Client) -> None:
    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return

        # Track message activity
        if message.guild:
            try:
                from ..database import get_db
                get_db().increment_activity(str(message.guild.id), "messages")
            except Exception:
                pass

        from ..features.registry import dispatch_on_message
        await dispatch_on_message(message)
