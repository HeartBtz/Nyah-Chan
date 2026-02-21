"""Basic text commands (!ping, !help, !roles, !stats)."""
from __future__ import annotations

import logging

import discord

from .registry import register
from ..database import get_db
from ..utils import format_uptime

logger = logging.getLogger("nyahchan.feature.commands")


class CommandsFeature:
    name = "commands"

    def setup(self, client: discord.Client) -> None:
        self._client = client

    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        cfg = get_db().get_guild_config(str(message.guild.id))
        prefix = cfg.get("prefix", "!")
        content = message.content or ""
        if not content.startswith(prefix):
            return None

        body = content[len(prefix):].strip()
        cmd = body.split()[0].lower() if body else ""
        if not cmd:
            return None

        if cmd == "ping":
            lat = round(self._client.latency * 1000) if self._client else 0
            embed = discord.Embed(
                title="🏓 Pong !",
                description=f"Latence: **{lat}ms**",
                color=discord.Color.green(),
            )
            await message.channel.send(embed=embed)

        elif cmd in ("help", "aide"):
            embed = discord.Embed(
                title="📖 Aide — Nyah-Chan",
                description="Voici les commandes disponibles :",
                color=discord.Color.blurple(),
            )
            embed.add_field(
                name="📌 Commandes générales",
                value=(
                    f"`{prefix}ping` — Latence du bot\n"
                    f"`{prefix}help` — Cette aide\n"
                    f"`{prefix}roles` — Rôles du serveur\n"
                    f"`{prefix}stats` — Statistiques du bot"
                ),
                inline=False,
            )
            embed.add_field(
                name="⚔️ Modération (slash)",
                value=(
                    "`/ban` `/kick` `/timeout` `/tempban` — Modération\n"
                    "`/warn` `/warnings` `/unwarn` — Avertissements\n"
                    "`/purge` — Supprimer des messages"
                ),
                inline=False,
            )
            embed.add_field(
                name="ℹ️ Info (slash)",
                value="`/userinfo` `/avatar` `/serverinfo`",
                inline=False,
            )
            embed.add_field(
                name="🎮 Engagement (slash)",
                value=(
                    "`/rank` — Voir son niveau et XP\n"
                    "`/leaderboard` — Classement XP du serveur\n"
                    "`/poll` — Créer un sondage\n"
                    "`/giveaway` — Lancer un giveaway\n"
                    "`/remind` — Rappel personnel\n"
                    "`/ticket` — Envoyer un embed de tickets"
                ),
                inline=False,
            )
            embed.add_field(
                name="🤖 Fonctionnalités",
                value=(
                    "**Role triggers** · **Keyword responses** · **Grant commands**\n"
                    "**Custom commands** · **Reaction roles** · **Starboard**\n"
                    "**Anti-raid** · **Anti-spam** · **Anti-lien** · **Audit logs**\n"
                    "**XP/Niveaux** · **Tickets** · **Messages programmés**\n"
                    "**Ollama Q&A** · **Auto-modération**\n"
                    "Tout est configurable via le panel web."
                ),
                inline=False,
            )
            await message.channel.send(embed=embed)

        elif cmd == "roles":
            if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_roles:
                roles = sorted(message.guild.roles, key=lambda r: r.position, reverse=True)
                lines = [f"`{r.position:>3}` {r.mention} ({len(r.members)} membres)" for r in roles[:30]]
                embed = discord.Embed(
                    title=f"📋 Rôles — {message.guild.name}",
                    description="\n".join(lines) or "Aucun rôle",
                    color=discord.Color.blurple(),
                )
                if len(roles) > 30:
                    embed.set_footer(text=f"Affichage 30/{len(roles)} rôles")
                await message.channel.send(embed=embed)
            else:
                await message.channel.send(
                    embed=discord.Embed(description="🚫 Permission `manage_roles` requise.", color=discord.Color.red())
                )

        elif cmd == "stats":
            from ..main import bot_state
            uptime = format_uptime(bot_state.get("started_at", ""))
            c = self._client
            embed = discord.Embed(title="📊 Statistiques — Nyah-Chan", color=discord.Color.purple())
            embed.add_field(name="Serveurs", value=str(len(c.guilds)), inline=True)
            embed.add_field(name="Utilisateurs", value=str(sum(g.member_count or 0 for g in c.guilds)), inline=True)
            embed.add_field(name="Latence", value=f"{round(c.latency * 1000)}ms", inline=True)
            embed.add_field(name="Uptime", value=uptime, inline=True)
            await message.channel.send(embed=embed)
        else:
            return None

        return None


register(CommandsFeature())
