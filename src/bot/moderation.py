from __future__ import annotations

from typing import Optional, List
from datetime import timedelta
import os

import logging
import discord
from discord import app_commands

from .moderation_store import WarningStore, WarningEntry

logger = logging.getLogger("nyahchan.moderation")


def _format_user_label(user: discord.abc.User) -> str:
    return f"{user} (`{user.id}`)"


def _get_mod_log_channel(guild: discord.Guild | None, client: discord.Client) -> discord.abc.Messageable | None:
    """Retourne le salon de logs de modération configuré via MOD_LOG_CHANNEL_ID.

    Si la variable n'est pas définie ou que le salon est introuvable, retourne None.
    """

    if guild is None:
        return None

    channel_id_raw = os.getenv("MOD_LOG_CHANNEL_ID")
    if not channel_id_raw:
        return None

    try:
        channel_id = int(channel_id_raw)
    except ValueError:
        logger.error(f"MOD_LOG_CHANNEL_ID invalide: {channel_id_raw!r}")
        return None

    channel = guild.get_channel(channel_id) or client.get_channel(channel_id)
    if channel is None or not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel)):
        logger.warning(f"Salon de log de modération introuvable pour ID {channel_id}")
        return None

    return channel


class ModerationCommands:
    def __init__(self, client: discord.Client) -> None:
        self.client = client
        self.tree = app_commands.CommandTree(client)
        self.warning_store = WarningStore()
        self._register_commands()

    def _register_commands(self) -> None:
        @self.tree.command(name="ban", description="Bannir un membre avec une raison")
        @app_commands.checks.has_permissions(ban_members=True)
        async def ban(
            interaction: discord.Interaction,
            member: discord.Member,
            reason: Optional[str] = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "Cette commande ne peut être utilisée que sur un serveur.",
                    ephemeral=True,
                )
                return

            if member == interaction.user:
                await interaction.response.send_message(
                    "Tu ne peux pas te bannir toi-même.",
                    ephemeral=True,
                )
                return

            reason_text = reason or "Aucune raison spécifiée."
            member_label = _format_user_label(member)
            moderator_label = _format_user_label(interaction.user)

            embed = discord.Embed(
                title="🚫 Bannissement",
                description=f"{member.mention} a été banni.",
                color=discord.Color.red(),
            )
            embed.add_field(name="Membre", value=member_label, inline=False)
            embed.add_field(name="Modérateur", value=moderator_label, inline=False)
            embed.add_field(name="Raison", value=reason_text, inline=False)

            # Accuser réception rapidement pour éviter le "ne répond pas"
            await interaction.response.defer(ephemeral=False)

            # Tenter d'informer le membre en DM, sans bloquer en cas d'échec
            try:
                await member.send(
                    f"Tu as été banni de **{interaction.guild.name}**.\nRaison: {reason_text}"
                )
            except Exception:
                # DM refusés ou impossibles : on ignore
                pass

            # Appliquer le bannissement
            try:
                await interaction.guild.ban(member, reason=reason_text)
            except Exception as e:
                embed.add_field(name="Erreur technique", value=str(e), inline=False)

            # Envoyer le résultat dans le salon où la commande a été utilisée
            await interaction.followup.send(embed=embed)

            # Log dans le salon de modération si configuré
            log_channel = _get_mod_log_channel(interaction.guild, self.client)
            if log_channel is not None:
                try:
                    await log_channel.send(embed=embed)
                except Exception:
                    pass

        @self.tree.command(name="kick", description="Expulser un membre avec une raison")
        @app_commands.checks.has_permissions(kick_members=True)
        async def kick(
            interaction: discord.Interaction,
            member: discord.Member,
            reason: Optional[str] = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "Cette commande ne peut être utilisée que sur un serveur.",
                    ephemeral=True,
                )
                return

            if member == interaction.user:
                await interaction.response.send_message(
                    "Tu ne peux pas te kick toi-même.",
                    ephemeral=True,
                )
                return

            reason_text = reason or "Aucune raison spécifiée."
            member_label = _format_user_label(member)
            moderator_label = _format_user_label(interaction.user)

            embed = discord.Embed(
                title="🚪 Expulsion",
                description=f"{member.mention} a été expulsé.",
                color=discord.Color.orange(),
            )
            embed.add_field(name="Membre", value=member_label, inline=False)
            embed.add_field(name="Modérateur", value=moderator_label, inline=False)
            embed.add_field(name="Raison", value=reason_text, inline=False)

            try:
                await member.send(
                    f"Tu as été expulsé de **{interaction.guild.name}**.\nRaison: {reason_text}"
                )
            except Exception:
                pass

            await interaction.guild.kick(member, reason=reason_text)
            await interaction.response.send_message(embed=embed)

            # Log dans le salon de modération si configuré
            log_channel = _get_mod_log_channel(interaction.guild, self.client)
            if log_channel is not None:
                try:
                    await log_channel.send(embed=embed)
                except Exception:
                    pass

        @self.tree.command(
            name="timeout",
            description="Mettre un membre en timeout pendant un certain nombre de minutes",
        )
        @app_commands.checks.has_permissions(moderate_members=True)
        async def timeout(
            interaction: discord.Interaction,
            member: discord.Member,
            minutes: app_commands.Range[int, 1, 43200],
            reason: Optional[str] = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "Cette commande ne peut être utilisée que sur un serveur.",
                    ephemeral=True,
                )
                return

            if member == interaction.user:
                await interaction.response.send_message(
                    "Tu ne peux pas te mettre en timeout toi-même.",
                    ephemeral=True,
                )
                return

            reason_text = reason or "Aucune raison spécifiée."
            member_label = _format_user_label(member)
            moderator_label = _format_user_label(interaction.user)

            until = discord.utils.utcnow() + timedelta(minutes=minutes)

            embed = discord.Embed(
                title="⏱ Timeout",
                description=f"{member.mention} est en timeout pour {minutes} minute(s).",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Membre", value=member_label, inline=False)
            embed.add_field(name="Modérateur", value=moderator_label, inline=False)
            embed.add_field(name="Durée", value=f"{minutes} minute(s)", inline=False)
            embed.add_field(name="Raison", value=reason_text, inline=False)

            try:
                await member.send(
                    f"Tu as été mis en timeout sur **{interaction.guild.name}** "
                    f"pour {minutes} minute(s).\nRaison: {reason_text}"
                )
            except Exception:
                pass

            await member.timeout(until, reason=reason_text)
            await interaction.response.send_message(embed=embed)

            # Log dans le salon de modération si configuré
            log_channel = _get_mod_log_channel(interaction.guild, self.client)
            if log_channel is not None:
                try:
                    await log_channel.send(embed=embed)
                except Exception:
                    pass

        @self.tree.command(name="warn", description="Ajouter un avertissement à un membre")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warn(
            interaction: discord.Interaction,
            member: discord.Member,
            reason: Optional[str] = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "Cette commande ne peut être utilisée que sur un serveur.",
                    ephemeral=True,
                )
                return

            if member == interaction.user:
                await interaction.response.send_message(
                    "Tu ne peux pas te warn toi-même.", ephemeral=True
                )
                return

            assert interaction.user is not None
            reason_text = reason or "Aucune raison spécifiée."

            entry = self.warning_store.add_warning(
                guild_id=interaction.guild.id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                reason=reason_text,
            )

            member_label = _format_user_label(member)
            moderator_label = _format_user_label(interaction.user)

            embed = discord.Embed(
                title="⚠️ Avertissement",
                description=f"{member.mention} a reçu un avertissement.",
                color=discord.Color.yellow(),
            )
            embed.add_field(name="ID de l'avertissement", value=str(entry.id), inline=False)
            embed.add_field(name="Membre", value=member_label, inline=False)
            embed.add_field(name="Modérateur", value=moderator_label, inline=False)
            embed.add_field(name="Raison", value=reason_text, inline=False)

            await interaction.response.send_message(embed=embed)

            # Log dans le salon de modération si configuré
            log_channel = _get_mod_log_channel(interaction.guild, self.client)
            if log_channel is not None:
                try:
                    await log_channel.send(embed=embed)
                except Exception:
                    pass

        @self.tree.command(name="warnings", description="Lister les avertissements d'un membre")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warnings_cmd(
            interaction: discord.Interaction,
            member: discord.Member,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "Cette commande ne peut être utilisée que sur un serveur.",
                    ephemeral=True,
                )
                return

            warns: List[WarningEntry] = self.warning_store.get_warnings(
                guild_id=interaction.guild.id,
                user_id=member.id,
            )

            if not warns:
                await interaction.response.send_message(
                    f"{member.mention} n'a aucun avertissement.",
                    ephemeral=True,
                )
                return

            member_label = _format_user_label(member)
            embed = discord.Embed(
                title="📋 Avertissements",
                description=f"Avertissements pour {member_label}",
                color=discord.Color.yellow(),
            )

            # Limiter pour éviter des embeds trop gros
            for w in warns[:10]:
                mod = f"<@{w.moderator_id}> ({w.moderator_id})"
                value = (
                    f"ID: `{w.id}`\n"
                    f"Modérateur: {mod}\n"
                    f"Date: {w.created_at}\n"
                    f"Raison: {w.reason}"
                )
                embed.add_field(name=f"Warn #{w.id}", value=value, inline=False)

            if len(warns) > 10:
                embed.set_footer(text=f"{len(warns)} avertissement(s) au total, affichage des 10 plus récents.")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        @self.tree.command(name="unwarn", description="Supprimer un avertissement d'un membre")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def unwarn(
            interaction: discord.Interaction,
            member: discord.Member,
            warning_id: int,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "Cette commande ne peut être utilisée que sur un serveur.",
                    ephemeral=True,
                )
                return

            ok = self.warning_store.remove_warning(
                guild_id=interaction.guild.id,
                user_id=member.id,
                warning_id=warning_id,
            )
            if not ok:
                await interaction.response.send_message(
                    f"Aucun avertissement avec l'ID `{warning_id}` pour {member.mention}.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                f"Avertissement `{warning_id}` supprimé pour {member.mention}.",
                ephemeral=True,
            )

    async def sync(self) -> None:
        try:
            await self.tree.sync()
            logger.info("Commandes de modération synchronisées avec Discord.")
        except Exception as e:
            logger.error(f"Échec de la synchronisation des commandes de modération: {e}")
