from __future__ import annotations

import logging
import os

import discord

logger = logging.getLogger("nyahchan.events.member_join")


def setup_member_join_event(client: discord.Client) -> None:
    # Cache env vars once at setup time, not on every event
    _enabled = os.getenv("WELCOME_ENABLED", "0") == "1"
    _channel_id_raw = os.getenv("WELCOME_CHANNEL_ID", "")
    _template = os.getenv(
        "WELCOME_MESSAGE",
        "Bienvenue {mention} sur **{server}** ! 🎉",
    )

    try:
        _channel_id = int(_channel_id_raw) if _channel_id_raw else None
    except ValueError:
        logger.warning("WELCOME_CHANNEL_ID invalid: %r", _channel_id_raw)
        _channel_id = None

    @client.event
    async def on_member_join(member: discord.Member) -> None:
        """Send a welcome message when a new member joins."""
        if not _enabled or _channel_id is None:
            return

        channel = member.guild.get_channel(_channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return

        message_text = _template.format(
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

    # --- Goodbye event ---
    _goodbye_enabled = os.getenv("GOODBYE_ENABLED", "0") == "1"
    _goodbye_channel_raw = os.getenv("GOODBYE_CHANNEL_ID", "")
    _goodbye_template = os.getenv(
        "GOODBYE_MESSAGE",
        "**{user}** a quitté **{server}**. Au revoir ! 👋",
    )

    try:
        _goodbye_channel_id = int(_goodbye_channel_raw) if _goodbye_channel_raw else None
    except ValueError:
        logger.warning("GOODBYE_CHANNEL_ID invalid: %r", _goodbye_channel_raw)
        _goodbye_channel_id = None

    @client.event
    async def on_member_remove(member: discord.Member) -> None:
        """Send a goodbye message when a member leaves."""
        if not _goodbye_enabled or _goodbye_channel_id is None:
            return

        channel = member.guild.get_channel(_goodbye_channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return

        message_text = _goodbye_template.format(
            mention=member.mention,
            user=str(member),
            username=member.name,
            server=member.guild.name,
            member_count=member.guild.member_count or "?",
        )

        embed = discord.Embed(
            title="👋 Départ",
            description=message_text,
            color=discord.Color.dark_grey(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed)
            logger.info("Goodbye message sent for %s in %s", member, member.guild.name)
        except Exception as e:
            logger.error("Failed to send goodbye message: %s", e)
