from __future__ import annotations

import logging
import os

import discord

logger = logging.getLogger("nyahchan.events.member_join")


def setup_member_join_event(client: discord.Client) -> None:
    @client.event
    async def on_member_join(member: discord.Member) -> None:
        """Send a welcome message when a new member joins."""
        enabled = os.getenv("WELCOME_ENABLED", "0") == "1"
        if not enabled:
            return

        channel_id_raw = os.getenv("WELCOME_CHANNEL_ID", "")
        if not channel_id_raw:
            return

        try:
            channel_id = int(channel_id_raw)
        except ValueError:
            logger.warning("WELCOME_CHANNEL_ID invalid: %r", channel_id_raw)
            return

        channel = member.guild.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            logger.warning("Welcome channel %d not found in guild %s", channel_id, member.guild.name)
            return

        template = os.getenv(
            "WELCOME_MESSAGE",
            "Bienvenue {mention} sur **{server}** ! 🎉",
        )

        message_text = template.format(
            mention=member.mention,
            user=str(member),
            username=member.name,
            server=member.guild.name,
            member_count=member.guild.member_count or "?",
        )

        embed = discord.Embed(
            title="👋 Nouveau membre !",
            description=message_text,
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Membre #{member.guild.member_count or '?'}")

        try:
            await channel.send(embed=embed)
            logger.info("Welcome message sent for %s in %s", member, member.guild.name)
        except Exception as e:
            logger.error("Failed to send welcome message: %s", e)
