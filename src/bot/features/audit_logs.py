"""Advanced audit logging — message edit/delete, voice state, nickname changes."""
from __future__ import annotations

import logging

import discord

from ..database import get_db

logger = logging.getLogger("nyahchan.feature.audit_logs")


def _get_audit_channel(guild: discord.Guild, client: discord.Client):
    cfg = get_db().get_guild_config(str(guild.id))
    if not cfg.get("audit_log_enabled"):
        return None
    ch_id = cfg.get("audit_log_channel_id")
    if not ch_id:
        return None
    try:
        ch = guild.get_channel(int(ch_id)) or client.get_channel(int(ch_id))
    except (ValueError, TypeError):
        return None
    if isinstance(ch, (discord.TextChannel, discord.Thread)):
        return ch
    return None


def setup_audit_logs(client: discord.Client) -> None:

    @client.event
    async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return
        ch = _get_audit_channel(before.guild, client)
        if not ch:
            return
        embed = discord.Embed(
            title="📝 Message modifié",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="Salon", value=before.channel.mention, inline=True)
        embed.add_field(
            name="Avant",
            value=(before.content or "(vide)")[:1024],
            inline=False,
        )
        embed.add_field(
            name="Après",
            value=(after.content or "(vide)")[:1024],
            inline=False,
        )
        embed.add_field(name="Lien", value=f"[Aller au message]({after.jump_url})", inline=False)
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    @client.event
    async def on_message_delete(message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        ch = _get_audit_channel(message.guild, client)
        if not ch:
            return
        embed = discord.Embed(
            title="🗑️ Message supprimé",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
        embed.add_field(
            name="Contenu",
            value=(message.content or "(vide)")[:1024],
            inline=False,
        )
        if message.attachments:
            embed.add_field(
                name="Pièces jointes",
                value="\n".join(a.filename for a in message.attachments),
                inline=False,
            )
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    @client.event
    async def on_voice_state_update(member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if member.bot:
            return
        ch = _get_audit_channel(member.guild, client)
        if not ch:
            return

        if before.channel is None and after.channel is not None:
            desc = f"🔊 {member.mention} a rejoint **{after.channel.name}**"
            color = discord.Color.green()
        elif before.channel is not None and after.channel is None:
            desc = f"🔇 {member.mention} a quitté **{before.channel.name}**"
            color = discord.Color.red()
        elif before.channel != after.channel:
            desc = (f"🔄 {member.mention} s'est déplacé de "
                    f"**{before.channel.name}** vers **{after.channel.name}**")
            color = discord.Color.blue()
        else:
            return

        embed = discord.Embed(
            title="🎙️ Activité vocale",
            description=desc,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    @client.event
    async def on_member_update(before: discord.Member, after: discord.Member) -> None:
        if before.bot:
            return
        if before.nick == after.nick:
            return
        ch = _get_audit_channel(before.guild, client)
        if not ch:
            return
        embed = discord.Embed(
            title="✏️ Changement de pseudo",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        embed.add_field(name="Avant", value=before.nick or before.name, inline=True)
        embed.add_field(name="Après", value=after.nick or after.name, inline=True)
        try:
            await ch.send(embed=embed)
        except Exception:
            pass
