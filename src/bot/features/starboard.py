"""Starboard — repost messages that receive enough star reactions."""
from __future__ import annotations

import logging

import discord

from ..database import get_db

logger = logging.getLogger("nyahchan.feature.starboard")


class StarboardMonitor:
    def __init__(self) -> None:
        self._client: discord.Client | None = None

    def setup(self, client: discord.Client) -> None:
        self._client = client

        @client.event
        async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
            await self._handle_reaction(payload)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id:
            return

        gid = str(payload.guild_id)
        cfg = get_db().get_guild_config(gid)
        if not cfg.get("starboard_enabled"):
            return

        star_emoji = cfg.get("starboard_emoji", "⭐")
        if str(payload.emoji) != star_emoji and payload.emoji.name != star_emoji:
            return

        threshold = int(cfg.get("starboard_threshold", 3))
        board_ch_id = cfg.get("starboard_channel_id")
        if not board_ch_id:
            return

        guild = self._client.get_guild(payload.guild_id)
        if not guild:
            return

        board_channel = guild.get_channel(int(board_ch_id))
        if not isinstance(board_channel, discord.TextChannel):
            return

        # Get the source message
        source_channel = guild.get_channel(payload.channel_id)
        if not isinstance(source_channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            msg = await source_channel.fetch_message(payload.message_id)
        except Exception:
            return

        # Don't starboard messages from the starboard channel
        if msg.channel.id == board_channel.id:
            return

        # Count star reactions
        star_count = 0
        for reaction in msg.reactions:
            if str(reaction.emoji) == star_emoji or getattr(reaction.emoji, 'name', '') == star_emoji:
                star_count = reaction.count
                break

        if star_count < threshold:
            return

        db = get_db()
        src_id = str(msg.id)

        # Check if already posted
        existing = db.get_starboard_entry(gid, src_id)

        embed = discord.Embed(
            description=msg.content or "",
            color=discord.Color.gold(),
            timestamp=msg.created_at,
        )
        embed.set_author(
            name=str(msg.author),
            icon_url=msg.author.display_avatar.url,
        )
        if msg.attachments:
            embed.set_image(url=msg.attachments[0].url)
        embed.add_field(
            name="Source",
            value=f"[Aller au message]({msg.jump_url})",
            inline=False,
        )

        header = f"{star_emoji} **{star_count}** | {source_channel.mention}"

        try:
            if existing:
                # Update existing starboard message
                try:
                    board_msg = await board_channel.fetch_message(int(existing))
                    await board_msg.edit(content=header, embed=embed)
                except discord.NotFound:
                    board_msg = await board_channel.send(content=header, embed=embed)
                    db.save_starboard_entry(gid, src_id, str(board_msg.id))
            else:
                board_msg = await board_channel.send(content=header, embed=embed)
                db.save_starboard_entry(gid, src_id, str(board_msg.id))
        except Exception as e:
            logger.error("[starboard] Failed: %s", e)


_starboard = StarboardMonitor()


def setup_starboard(client: discord.Client) -> None:
    _starboard.setup(client)
