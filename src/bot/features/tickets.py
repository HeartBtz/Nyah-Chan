"""Ticket system — create private support channels on button click."""
from __future__ import annotations

import logging

import discord
from discord import ui

from ..database import get_db

logger = logging.getLogger("nyahchan.feature.tickets")


class TicketOpenButton(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="📩 Ouvrir un ticket", style=discord.ButtonStyle.green, custom_id="nyah_ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("Serveur uniquement.", ephemeral=True)

        gid = str(interaction.guild.id)
        cfg = get_db().get_guild_config(gid)
        if not cfg.get("tickets_enabled"):
            return await interaction.response.send_message("Le système de tickets est désactivé.", ephemeral=True)

        # Check if user already has an open ticket
        existing = discord.utils.get(
            interaction.guild.text_channels,
            name=f"ticket-{interaction.user.name}".lower().replace(" ", "-")[:100],
        )
        if existing:
            return await interaction.response.send_message(
                f"Tu as déjà un ticket ouvert : {existing.mention}", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # Get category
        category = None
        cat_id = cfg.get("tickets_category_id")
        if cat_id:
            try:
                category = interaction.guild.get_channel(int(cat_id))
            except (ValueError, TypeError):
                pass

        # Permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
        }

        # Add support role
        support_role_name = cfg.get("tickets_support_role")
        if support_role_name:
            role = discord.utils.get(interaction.guild.roles, name=support_role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True
                )

        channel_name = f"ticket-{interaction.user.name}"[:100]
        try:
            ticket_ch = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket ouvert par {interaction.user}",
            )
        except Exception as e:
            logger.error("[tickets] create channel failed: %s", e)
            return await interaction.followup.send("Erreur lors de la création du ticket.", ephemeral=True)

        # Welcome message in ticket
        embed = discord.Embed(
            title="🎟️ Ticket ouvert",
            description=(
                f"Bienvenue {interaction.user.mention} !\n\n"
                "Décris ton problème ci-dessous, le staff te répondra dès que possible.\n"
                "Clique sur **Fermer le ticket** quand ton problème est résolu."
            ),
            color=discord.Color.green(),
        )
        await ticket_ch.send(embed=embed, view=TicketCloseButton())
        await interaction.followup.send(f"Ticket créé : {ticket_ch.mention}", ephemeral=True)


class TicketCloseButton(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="nyah_ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if not interaction.guild or not interaction.channel:
            return

        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel) or not ch.name.startswith("ticket-"):
            return await interaction.response.send_message("Ce n'est pas un ticket.", ephemeral=True)

        await interaction.response.defer()

        # Log to tickets log channel
        gid = str(interaction.guild.id)
        cfg = get_db().get_guild_config(gid)
        log_ch_id = cfg.get("tickets_log_channel_id")
        if log_ch_id:
            log_ch = interaction.guild.get_channel(int(log_ch_id))
            if isinstance(log_ch, discord.TextChannel):
                embed = discord.Embed(
                    title="🎟️ Ticket fermé",
                    description=f"**{ch.name}** fermé par {interaction.user.mention}",
                    color=discord.Color.red(),
                )
                try:
                    await log_ch.send(embed=embed)
                except Exception:
                    pass

        try:
            await ch.delete(reason=f"Ticket fermé par {interaction.user}")
        except Exception as e:
            logger.error("[tickets] delete channel failed: %s", e)
            await interaction.followup.send("Erreur lors de la fermeture.", ephemeral=True)


def setup_tickets(client: discord.Client) -> None:
    # Register persistent views so buttons work after restart
    client.add_view(TicketOpenButton())
    client.add_view(TicketCloseButton())
