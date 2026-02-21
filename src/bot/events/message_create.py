from __future__ import annotations

import logging

import discord

from ..features.registry import dispatch_on_message

logger = logging.getLogger("nyahchan.events.message")


def setup_message_event(client: discord.Client) -> None:
    @client.event
    async def on_message(message: discord.Message) -> None:
        # Ignore bots and DMs
        if message.author.bot or message.guild is None:
            return
        await dispatch_on_message(message)
