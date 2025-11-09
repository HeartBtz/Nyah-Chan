import os
import discord
from ..services.roles import assign_or_remove_role


def setup_message_event(client: discord.Client):
    @client.event
    async def on_message(message: discord.Message):
        # Ignore bots and DMs
        if message.author.bot or message.guild is None:
            return
        await assign_or_remove_role(message)
