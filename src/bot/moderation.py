from __future__ import annotations

import logging
import os
from datetime import timedelta, timezone
from typing import List, Optional

import discord
from discord import app_commands

from .moderation_store import WarningEntry, WarningStore

logger = logging.getLogger("nyahchan.moderation")


def _format_user_label(user: discord.abc.User) -> str:
    return f"{user} (`{user.id}`)"


def _get_mod_log_channel(
    guild: discord.Guild | None, client: discord.Client
) -> discord.abc.Messageable | None:
    """Return the configured moderation log channel, or None."""
    if guild is None:
        return None

    channel_id_raw = os.getenv("MOD_LOG_CHANNEL_ID")
    if not channel_id_raw:
        return None

    try:
        channel_id = int(channel_id_raw)
    except ValueError:
        logger.error("MOD_LOG_CHANNEL_ID invalid: %r", channel_id_raw)
        return None

    channel = guild.get_channel(channel_id) or client.get_channel(channel_id)
    if channel is None or not isinstance(
        channel,
        (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel),
    ):
        logger.warning("Moderation log channel not found for ID %d", channel_id)
        return None

    return channel


async def _send_log(guild: discord.Guild | None, client: discord.Client, embed: discord.Embed) -> None:
    """Send an embed to the moderation log channel, silently ignoring errors."""
    log_channel = _get_mod_log_channel(guild, client)
    if log_channel is not None:
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            logger.debug("Failed to send mod log: %s", e)


class ModerationCommands:
    def __init__(self, client: discord.Client) -> None:
        self.client = client
        self.tree = app_commands.CommandTree(client)
        self.warning_store = WarningStore()
        self._register_commands()
        self._register_error_handlers()

    def _register_error_handlers(self) -> None:
        """Global error handler for slash commands."""

        @self.tree.error
        async def on_app_command_error(
            interaction: discord.Interaction, error: app_commands.AppCommandError
        ) -> None:
            if isinstance(error, app_commands.MissingPermissions):
                missing = ", ".join(error.missing_permissions)
                msg = f"🚫 Permission(s) manquante(s): `{missing}`"
            elif isinstance(error, app_commands.BotMissingPermissions):
                missing = ", ".join(error.missing_permissions)
                msg = f"🚫 Je n'ai pas les permissions requises: `{missing}`"
            elif isinstance(error, app_commands.CommandOnCooldown):
                msg = f"⏳ Commande en cooldown. Réessaie dans {error.retry_after:.1f}s."
            else:
                msg = f"❌ Une erreur est survenue: {error}"
                logger.error("Slash command error: %s", error, exc_info=error)

            try:
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                pass

    def _register_commands(self) -> None:
        # --- /userinfo ---
        @self.tree.command(name="userinfo", description="Afficher les informations d'un utilisateur")
        async def userinfo(
            interaction: discord.Interaction,
            member: Optional[discord.Member] = None,
        ) -> None:
            target = member or interaction.user
            if target is None:
                await interaction.response.send_message("Impossible de déterminer l'utilisateur.", ephemeral=True)
                return

            embed = discord.Embed(title=f"Infos — {target}", color=discord.Color.blurple())
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.add_field(name="ID", value=f"`{target.id}`", inline=True)
            embed.add_field(
                name="Compte créé le",
                value=discord.utils.format_dt(target.created_at, style="R"),
                inline=True,
            )

            if isinstance(target, discord.Member):
                embed.add_field(
                    name="A rejoint le",
                    value=discord.utils.format_dt(target.joined_at, style="R") if target.joined_at else "(inconnu)",
                    inline=True,
                )
                roles = [r.mention for r in target.roles if not r.is_default()]
                roles_text = ", ".join(roles[:20]) if roles else "Aucun rôle"
                if len(roles) > 20:
                    roles_text += f" (+{len(roles) - 20} autres)"
                embed.add_field(name=f"Rôles [{len(roles)}]", value=roles_text, inline=False)

            embed.add_field(name="Bot", value="Oui" if target.bot else "Non", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # --- /avatar ---
        @self.tree.command(name="avatar", description="Afficher l'avatar d'un utilisateur")
        async def avatar(
            interaction: discord.Interaction,
            member: Optional[discord.Member] = None,
        ) -> None:
            target = member or interaction.user
            if target is None:
                await interaction.response.send_message("Impossible de déterminer l'utilisateur.", ephemeral=True)
                return

            embed = discord.Embed(title=f"Avatar de {target}", color=discord.Color.blurple())
            embed.set_image(url=target.display_avatar.with_size(1024).url)
            await interaction.response.send_message(embed=embed)

        # --- /serverinfo ---
        @self.tree.command(name="serverinfo", description="Afficher les informations du serveur")
        async def serverinfo(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("Utilisable uniquement sur un serveur.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"📊 {guild.name}",
                color=discord.Color.blurple(),
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            embed.add_field(name="Propriétaire", value=str(guild.owner) if guild.owner else "Inconnu", inline=True)
            embed.add_field(name="Membres", value=str(guild.member_count or 0), inline=True)
            embed.add_field(name="Rôles", value=str(len(guild.roles)), inline=True)
            embed.add_field(name="Salons texte", value=str(len(guild.text_channels)), inline=True)
            embed.add_field(name="Salons vocaux", value=str(len(guild.voice_channels)), inline=True)
            embed.add_field(name="Emojis", value=str(len(guild.emojis)), inline=True)
            embed.add_field(
                name="Créé le",
                value=discord.utils.format_dt(guild.created_at, style="F"),
                inline=False,
            )
            embed.add_field(
                name="Niveau de vérification",
                value=str(guild.verification_level).capitalize(),
                inline=True,
            )
            embed.add_field(name="Boosts", value=str(guild.premium_subscription_count), inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # --- /purge ---
        @self.tree.command(name="purge", description="Supprimer un nombre de messages dans le salon")
        @app_commands.checks.has_permissions(manage_messages=True)
        async def purge(
            interaction: discord.Interaction,
            count: app_commands.Range[int, 1, 200],
        ) -> None:
            if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("Utilisable uniquement dans un salon texte.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            try:
                deleted = await interaction.channel.purge(limit=count)
                await interaction.followup.send(f"🗑️ {len(deleted)} message(s) supprimé(s).", ephemeral=True)

                embed = discord.Embed(
                    title="🗑️ Purge",
                    description=f"{len(deleted)} messages supprimés dans {interaction.channel.mention}",
                    color=discord.Color.orange(),
                )
                embed.add_field(name="Modérateur", value=_format_user_label(interaction.user), inline=False)
                await _send_log(interaction.guild, self.client, embed)
            except Exception as e:
                await interaction.followup.send(f"Erreur: {e}", ephemeral=True)

        # --- /ban ---
        @self.tree.command(name="ban", description="Bannir un membre")
        @app_commands.checks.has_permissions(ban_members=True)
        async def ban(
            interaction: discord.Interaction,
            member: discord.Member,
            reason: Optional[str] = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
                return
            if member == interaction.user:
                await interaction.response.send_message("Tu ne peux pas te bannir toi-même.", ephemeral=True)
                return
            if member.top_role >= interaction.guild.me.top_role:
                await interaction.response.send_message(
                    "Je ne peux pas bannir ce membre (hiérarchie de rôles).", ephemeral=True
                )
                return

            reason_text = reason or "Aucune raison spécifiée."
            embed = discord.Embed(title="🚫 Bannissement", color=discord.Color.red())
            embed.add_field(name="Membre", value=_format_user_label(member), inline=False)
            embed.add_field(name="Modérateur", value=_format_user_label(interaction.user), inline=False)
            embed.add_field(name="Raison", value=reason_text, inline=False)

            await interaction.response.defer(ephemeral=False)

            # Try DM before ban
            try:
                await member.send(f"Tu as été banni de **{interaction.guild.name}**.\nRaison: {reason_text}")
            except Exception:
                pass

            try:
                await interaction.guild.ban(member, reason=reason_text)
                embed.description = f"{member.mention} a été banni."
            except Exception as e:
                embed.description = "Échec du bannissement."
                embed.add_field(name="Erreur", value=str(e), inline=False)
                logger.error("Ban failed: %s", e)

            await interaction.followup.send(embed=embed)
            await _send_log(interaction.guild, self.client, embed)

        # --- /kick ---
        @self.tree.command(name="kick", description="Expulser un membre")
        @app_commands.checks.has_permissions(kick_members=True)
        async def kick(
            interaction: discord.Interaction,
            member: discord.Member,
            reason: Optional[str] = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
                return
            if member == interaction.user:
                await interaction.response.send_message("Tu ne peux pas te kick toi-même.", ephemeral=True)
                return
            if member.top_role >= interaction.guild.me.top_role:
                await interaction.response.send_message(
                    "Je ne peux pas expulser ce membre (hiérarchie de rôles).", ephemeral=True
                )
                return

            reason_text = reason or "Aucune raison spécifiée."
            embed = discord.Embed(title="🚪 Expulsion", color=discord.Color.orange())
            embed.add_field(name="Membre", value=_format_user_label(member), inline=False)
            embed.add_field(name="Modérateur", value=_format_user_label(interaction.user), inline=False)
            embed.add_field(name="Raison", value=reason_text, inline=False)

            # BUGFIX: defer first to avoid interaction timeout
            await interaction.response.defer(ephemeral=False)

            try:
                await member.send(f"Tu as été expulsé de **{interaction.guild.name}**.\nRaison: {reason_text}")
            except Exception:
                pass

            try:
                await interaction.guild.kick(member, reason=reason_text)
                embed.description = f"{member.mention} a été expulsé."
            except Exception as e:
                embed.description = "Échec de l'expulsion."
                embed.add_field(name="Erreur", value=str(e), inline=False)
                logger.error("Kick failed: %s", e)

            await interaction.followup.send(embed=embed)
            await _send_log(interaction.guild, self.client, embed)

        # --- /timeout ---
        @self.tree.command(name="timeout", description="Mettre un membre en timeout")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def timeout(
            interaction: discord.Interaction,
            member: discord.Member,
            minutes: app_commands.Range[int, 1, 43200],
            reason: Optional[str] = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
                return
            if member == interaction.user:
                await interaction.response.send_message("Tu ne peux pas te mettre en timeout.", ephemeral=True)
                return

            # Hierarchy check
            if member.top_role >= interaction.guild.me.top_role:
                await interaction.response.send_message(
                    f"Je ne peux pas mettre en timeout {member.mention} — son rôle est trop élevé.",
                    ephemeral=True,
                )
                return

            reason_text = reason or "Aucune raison spécifiée."
            until = discord.utils.utcnow() + timedelta(minutes=minutes)

            embed = discord.Embed(title="⏱ Timeout", color=discord.Color.blurple())
            embed.add_field(name="Membre", value=_format_user_label(member), inline=False)
            embed.add_field(name="Modérateur", value=_format_user_label(interaction.user), inline=False)
            embed.add_field(name="Durée", value=f"{minutes} minute(s)", inline=True)
            embed.add_field(name="Raison", value=reason_text, inline=False)

            await interaction.response.defer(ephemeral=False)

            try:
                await member.send(
                    f"Tu as été mis en timeout sur **{interaction.guild.name}** "
                    f"pour {minutes} minute(s).\nRaison: {reason_text}"
                )
            except Exception:
                pass

            try:
                await member.timeout(until, reason=reason_text)
                embed.description = f"{member.mention} est en timeout pour {minutes} minute(s)."
            except Exception as e:
                embed.description = "Échec du timeout."
                embed.add_field(name="Erreur", value=str(e), inline=False)
                logger.error("Timeout failed: %s", e)

            await interaction.followup.send(embed=embed)
            await _send_log(interaction.guild, self.client, embed)

        # --- /warn ---
        @self.tree.command(name="warn", description="Ajouter un avertissement")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warn(
            interaction: discord.Interaction,
            member: discord.Member,
            reason: Optional[str] = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
                return
            if member == interaction.user:
                await interaction.response.send_message("Tu ne peux pas te warn toi-même.", ephemeral=True)
                return

            assert interaction.user is not None
            reason_text = reason or "Aucune raison spécifiée."

            entry = self.warning_store.add_warning(
                guild_id=interaction.guild.id,
                user_id=member.id,
                moderator_id=interaction.user.id,
                reason=reason_text,
            )

            embed = discord.Embed(
                title="⚠️ Avertissement",
                description=f"{member.mention} a reçu un avertissement.",
                color=discord.Color.yellow(),
            )
            embed.add_field(name="ID", value=f"`#{entry.id}`", inline=True)
            embed.add_field(name="Membre", value=_format_user_label(member), inline=False)
            embed.add_field(name="Modérateur", value=_format_user_label(interaction.user), inline=False)
            embed.add_field(name="Raison", value=reason_text, inline=False)

            # Count total warnings
            total = len(self.warning_store.get_warnings(interaction.guild.id, member.id))
            embed.set_footer(text=f"Total avertissements: {total}")

            await interaction.response.send_message(embed=embed)
            await _send_log(interaction.guild, self.client, embed)

        # --- /warnings ---
        @self.tree.command(name="warnings", description="Lister les avertissements d'un membre")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warnings_cmd(
            interaction: discord.Interaction,
            member: discord.Member,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
                return

            warns: List[WarningEntry] = self.warning_store.get_warnings(
                guild_id=interaction.guild.id, user_id=member.id,
            )

            if not warns:
                await interaction.response.send_message(
                    f"{member.mention} n'a aucun avertissement.", ephemeral=True,
                )
                return

            embed = discord.Embed(
                title=f"📋 Avertissements — {member}",
                description=f"{len(warns)} avertissement(s)",
                color=discord.Color.yellow(),
            )

            for w in warns[:10]:
                mod = f"<@{w.moderator_id}>"
                value = f"**Modérateur:** {mod}\n**Date:** {w.created_at}\n**Raison:** {w.reason}"
                embed.add_field(name=f"#{w.id}", value=value, inline=False)

            if len(warns) > 10:
                embed.set_footer(text=f"Affichage 10/{len(warns)} avertissements")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # --- /unwarn ---
        @self.tree.command(name="unwarn", description="Supprimer un avertissement")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def unwarn(
            interaction: discord.Interaction,
            member: discord.Member,
            warning_id: int,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
                return

            ok = self.warning_store.remove_warning(
                guild_id=interaction.guild.id, user_id=member.id, warning_id=warning_id,
            )
            if not ok:
                await interaction.response.send_message(
                    f"Aucun avertissement `#{warning_id}` pour {member.mention}.", ephemeral=True,
                )
                return

            await interaction.response.send_message(
                f"✅ Avertissement `#{warning_id}` supprimé pour {member.mention}.", ephemeral=True,
            )

    async def sync(self) -> None:
        """Sync slash commands with Discord."""
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d slash command(s) with Discord.", len(synced))
        except Exception as e:
            logger.error("Failed to sync slash commands: %s", e)
