import discord
from ..features.registry import dispatch_on_message


def setup_message_event(client: discord.Client):
    @client.event
    async def on_message(message: discord.Message):
        # Ignore bots and DMs
        if message.author.bot or message.guild is None:
            return
        await dispatch_on_message(message)
