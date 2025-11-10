from __future__ import annotations

import os
import logging
import discord
from .registry import register

logger = logging.getLogger("nyahchan.feature.commands")


class CommandsFeature:
    name = "commands"

    def setup(self, client: discord.Client) -> None:  # noqa: D401
        pass  # no special setup needed

    async def on_message(self, message: discord.Message) -> None:  # noqa: D401
        if message.author.bot or message.guild is None:
            return
        prefix = os.getenv("PREFIX", "!")
        content = message.content or ""
        if not content.startswith(prefix):
            return
        body = content[len(prefix):].strip().lower()
        if body == "ping":
            try:
                await message.channel.send("Pong!")
            except Exception:
                return
            logger.debug("ping command")
        elif body in ("help", "aide"):
            try:
                await message.channel.send(
                    "Commandes disponibles:\n"
                    f"{prefix}ping - test de réactivité\n"
                    f"{prefix}help - affiche cette aide\n"
                    f"Triggers de rôles: définis dans role_triggers.json ou .env"
                )
            except Exception:
                return
            logger.debug("help command")
        elif body == "roles":
            if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_roles:
                roles = sorted(message.guild.roles, key=lambda r: r.position, reverse=True)  # type: ignore[union-attr]
                lines = [f"{r.position:>3} | {r.name}" for r in roles]
                text = "Liste des rôles (haut -> bas):\n" + "\n".join(lines[:50])
                try:
                    await message.channel.send(f"```\n{text}\n```")
                except Exception:
                    return
                logger.debug("roles command")
            else:
                try:
                    await message.channel.send("Permission insuffisante pour !roles")
                except Exception:
                    pass


register(CommandsFeature())
