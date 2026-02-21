from __future__ import annotations

import os
import logging

import discord

from .registry import register
from ..utils import calculate_uptime

logger = logging.getLogger("nyahchan.feature.commands")


class CommandsFeature:
    name = "commands"

    def setup(self, client: discord.Client) -> None:
        self._client = client

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        prefix = os.getenv("PREFIX", "!")
        content = message.content or ""
        if not content.startswith(prefix):
            return
        body = content[len(prefix):].strip()
        cmd = body.split()[0].lower() if body else ""
        if not cmd:
            return

        if cmd == "ping":
            latency = round(self._client.latency * 1000) if self._client else 0
            embed = discord.Embed(
                title="🏓 Pong !",
                description=f"Latence: **{latency}ms**",
                color=discord.Color.green(),
            )
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass
            logger.debug("ping command by %s", message.author)

        elif cmd in ("help", "aide"):
            embed = discord.Embed(
                title="📖 Aide — Nyah-Chan",
                description="Voici les commandes disponibles :",
                color=discord.Color.blurple(),
            )
            embed.add_field(
                name="📌 Commandes générales",
                value=(
                    f"`{prefix}ping` — Tester la latence du bot\n"
                    f"`{prefix}help` — Afficher cette aide\n"
                    f"`{prefix}roles` — Lister les rôles du serveur\n"
                    f"`{prefix}stats` — Statistiques du bot"
                ),
                inline=False,
            )
            embed.add_field(
                name="⚔️ Modération (slash commands)",
                value=(
                    "`/ban` `/kick` `/timeout` — Actions de modération\n"
                    "`/warn` `/warnings` `/unwarn` — Avertissements\n"
                    "`/purge` — Supprimer des messages en masse"
                ),
                inline=False,
            )
            embed.add_field(
                name="ℹ️ Info (slash commands)",
                value=(
                    "`/userinfo` — Infos sur un utilisateur\n"
                    "`/avatar` — Avatar d'un utilisateur\n"
                    "`/serverinfo` — Infos du serveur"
                ),
                inline=False,
            )
            embed.add_field(
                name="🤖 Autres",
                value=(
                    "**Triggers de rôles** — Configurable via le panel web\n"
                    "**Keyword responses** — Embeds automatiques par mots-clés\n"
                    "**Grant commands** — Commandes d'attribution de rôles\n"
                    "**Q&A Ollama** — Mentionnez le bot avec `?` pour poser une question\n"
                    "**Auto-modération** — Anti-spam, mots interdits, CAPS (config .env)"
                ),
                inline=False,
            )
            embed.set_footer(text="Panel d'administration : /ui/keywords")
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass
            logger.debug("help command by %s", message.author)

        elif cmd == "roles":
            if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_roles:
                roles = sorted(message.guild.roles, key=lambda r: r.position, reverse=True)
                lines = [f"`{r.position:>3}` {r.mention} ({len(r.members)} membres)" for r in roles[:30]]
                embed = discord.Embed(
                    title=f"📋 Rôles — {message.guild.name}",
                    description="\n".join(lines) if lines else "Aucun rôle",
                    color=discord.Color.blurple(),
                )
                if len(roles) > 30:
                    embed.set_footer(text=f"Affichage 30/{len(roles)} rôles")
                try:
                    await message.channel.send(embed=embed)
                except Exception:
                    pass
            else:
                try:
                    await message.channel.send(
                        embed=discord.Embed(
                            description="🚫 Permission `manage_roles` requise.",
                            color=discord.Color.red(),
                        )
                    )
                except Exception:
                    pass

        elif cmd == "stats":
            client = self._client
            from ..main import bot_state
            uptime = calculate_uptime(bot_state.get("started_at", ""))

            embed = discord.Embed(
                title="📊 Statistiques — Nyah-Chan",
                color=discord.Color.purple(),
            )
            embed.add_field(name="Serveurs", value=str(len(client.guilds)), inline=True)
            embed.add_field(
                name="Utilisateurs",
                value=str(sum(g.member_count or 0 for g in client.guilds)),
                inline=True,
            )
            embed.add_field(name="Latence", value=f"{round(client.latency * 1000)}ms", inline=True)
            embed.add_field(name="Uptime", value=uptime, inline=True)
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass


register(CommandsFeature())
