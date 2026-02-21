"""on_message event — dispatch to feature registry."""
from __future__ import annotations

import discord


def setup_message_event(client: discord.Client) -> None:
    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        from ..features.registry import dispatch_on_message

        await dispatch_on_message(message)
