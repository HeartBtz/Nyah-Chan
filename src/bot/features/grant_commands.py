"""Grant commands — privileged role assignment, DB-backed."""
from __future__ import annotations

import logging
import os
from typing import Optional

import discord

from .registry import register
from ..database import get_db
from ..utils import ensure_role

logger = logging.getLogger("nyahchan.feature.grant")


class GrantCommandsFeature:
    name = "grant_commands"

    def setup(self, client: discord.Client) -> None:
        pass

    @staticmethod
    def _parse_target(message: discord.Message) -> Optional[discord.Member]:
        if message.mentions:
            m = message.mentions[0]
            return m if isinstance(m, discord.Member) else None
        try:
            parts = (message.content or "").split()
            if len(parts) >= 2:
                uid = int(parts[1].strip("<@!>"))
                return message.guild.get_member(uid)  # type: ignore[union-attr]
        except Exception:
            pass
        return None

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

        commands = get_db().get_grant_commands(str(message.guild.id))
        matched = next((c for c in commands if c.get("name", "").lower() == cmd), None)
        if matched is None:
            return None

        me = message.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return None

        # Permission check
        allowed = [int(x) for x in matched.get("allowed_user_ids", [])]
        if message.author.id not in allowed:
            await message.channel.send(
                embed=discord.Embed(
                    title="⛔ Accès refusé",
                    description="Tu n'as pas la permission d'utiliser cette commande.",
                    color=discord.Color.red(),
                ),
                delete_after=10,
            )
            return None

        target = self._parse_target(message)
        if target is None:
            await message.channel.send(
                embed=discord.Embed(
                    title="❓ Cible manquante",
                    description=f"Utilisation: `{prefix}{cmd} @membre`",
                    color=discord.Color.orange(),
                ),
                delete_after=10,
            )
            return None

        role = await ensure_role(message.guild, matched.get("role_name", ""))
        if role is None:
            await message.channel.send(
                embed=discord.Embed(
                    title="❌ Erreur",
                    description="Impossible de trouver ou créer le rôle.",
                    color=discord.Color.red(),
                )
            )
            return None

        if role.position >= me.top_role.position:
            await message.channel.send(
                embed=discord.Embed(
                    title="⚠️ Hiérarchie",
                    description=f"Mon rôle est trop bas pour gérer **{role.name}**.",
                    color=discord.Color.orange(),
                )
            )
            return None

        if role in target.roles:
            await message.channel.send(
                embed=discord.Embed(
                    title="ℹ️ Déjà attribué",
                    description=f"{target.mention} possède déjà **{role.name}**.",
                    color=discord.Color.blue(),
                ),
                delete_after=10,
            )
            return None

        try:
            await target.add_roles(role, reason=f"Grant '{cmd}' par {message.author}")
            embed = discord.Embed(
                title="✅ Rôle attribué",
                description=f"{target.mention} a reçu le rôle **{role.name}** !",
                color=discord.Color.green(),
            )
            embed.set_footer(text=f"Par {message.author.display_name}")
            await message.channel.send(embed=embed)

            gif_path = matched.get("gif_path")
            if gif_path:
                resolved = os.path.realpath(gif_path)
                allowed_base = os.path.realpath(".")
                if resolved.startswith(allowed_base) and os.path.isfile(resolved):
                    await message.channel.send(file=discord.File(resolved))
        except Exception as e:
            logger.error("Grant add_roles failed: %s", e)
            await message.channel.send(
                embed=discord.Embed(title="❌ Erreur", description=str(e), color=discord.Color.red())
            )

        return None


register(GrantCommandsFeature())
