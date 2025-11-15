from __future__ import annotations

from typing import Optional

import logging
import discord
from discord import app_commands

logger = logging.getLogger("nyahchan.moderation")


def _format_user_label(user: discord.abc.User) -> str:
    return f"{user} (`{user.id}`)"


class ModerationCommands:
    def __init__(self, client: discord.Client) -> None:
        self.client = client
        self.tree = app_commands.CommandTree(client)
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

            try:
                await member.send(
                    f"Tu as été banni de **{interaction.guild.name}**.\nRaison: {reason_text}"
                )
            except Exception:
                pass

            await interaction.guild.ban(member, reason=reason_text)
            await interaction.response.send_message(embed=embed)

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

            until = discord.utils.utcnow() + discord.timedelta(minutes=minutes)

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

    async def sync(self) -> None:
        try:
            await self.tree.sync()
            logger.info("Commandes de modération synchronisées avec Discord.")
        except Exception as e:
            logger.error(f"Échec de la synchronisation des commandes de modération: {e}")
