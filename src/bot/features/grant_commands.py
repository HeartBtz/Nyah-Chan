from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import List, Optional

import discord

from .registry import register
from ..config.grant_commands_store import load_grant_commands
from ..utils import ensure_role

logger = logging.getLogger("nyahchan.feature.grant")

CONFIG_ENV = "GRANT_COMMANDS_CONFIG"


@dataclass
class GrantCommand:
    name: str
    allowed_user_ids: List[int]
    role_name: str
    gif_path: str | None = None


class GrantCommandsFeature:
    name = "grant_commands"

    def __init__(self) -> None:
        self.prefix = os.getenv("PREFIX", "!")
        self.commands: List[GrantCommand] = []

    def _load_from_config(self) -> None:
        self.commands.clear()
        path = os.getenv(CONFIG_ENV, "grant_commands.json")
        try:
            data = load_grant_commands(path)
            for item in data.get("commands", []):
                    name = str(item.get("name", "")).strip().lower()
                    rname = str(item.get("role_name", "")).strip()
                    gif_path = item.get("gif_path")
                    ids_raw = item.get("allowed_user_ids", [])
                    ids: List[int] = []
                    for v in ids_raw:
                        try:
                            ids.append(int(str(v)))
                        except Exception:
                            pass
                    if name and rname and ids:
                        self.commands.append(GrantCommand(name=name, allowed_user_ids=ids, role_name=rname, gif_path=gif_path))
            logger.info(f"Chargé {len(self.commands)} commande(s) grant depuis {path}.")
        except Exception as e:
            logger.error(f"Erreur lecture {CONFIG_ENV}: {e}")
        if not self.commands:
            one_name = os.getenv("GRANT_CMD_NAME")
            one_role = os.getenv("GRANT_ROLE_NAME")
            one_gif = os.getenv("GRANT_GIF_PATH")
            ids_env = os.getenv("GRANT_ALLOWED_USER_IDS") or os.getenv("GRANT_USER_ID")
            if one_name and one_role and ids_env:
                try:
                    ids = [int(x.strip()) for x in ids_env.split(",") if x.strip()]
                except Exception:
                    ids = []
                if ids:
                    self.commands.append(GrantCommand(name=one_name.lower(), allowed_user_ids=ids, role_name=one_role, gif_path=one_gif))
                    logger.info("Fallback .env chargé pour grant_commands.")

    def setup(self, client: discord.Client) -> None:  # noqa: D401
        self._load_from_config()

    def reload(self) -> None:
        """Recharger la configuration des grant commands depuis le JSON/env."""
        self._load_from_config()

    async def _grant_ensure_role(self, guild: discord.Guild, role_name: str) -> Optional[discord.Role]:
        return await ensure_role(guild, role_name)

    def _parse_target_member(self, message: discord.Message) -> Optional[discord.Member]:
        if message.mentions:
            m = message.mentions[0]
            return m if isinstance(m, discord.Member) else None
        # Essayer de lire un ID brut après la commande
        try:
            parts = (message.content or "").split()
            if len(parts) >= 2:
                raw = parts[1].strip("<@!>")
                uid = int(raw)
                return message.guild.get_member(uid)  # type: ignore[union-attr]
        except Exception:
            pass
        return None

    async def on_message(self, message: discord.Message) -> None:  # noqa: D401
        if message.author.bot or message.guild is None:
            return

        content = message.content or ""
        if not content.startswith(self.prefix):
            return

        me = message.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return

        body = content[len(self.prefix):].strip()
        cmd = body.split()[0].lower() if body else ""
        if not cmd:
            return

        matched: Optional[GrantCommand] = None
        for gc in self.commands:
            if gc.name == cmd:
                matched = gc
                break
        if matched is None:
            return

        # Permission check
        if message.author.id not in matched.allowed_user_ids:
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Tu n'as pas la permission d'utiliser cette commande.",
                color=discord.Color.red(),
            )
            try:
                await message.channel.send(embed=embed, delete_after=10)
            except Exception:
                pass
            return

        # Find target
        target = self._parse_target_member(message)
        if target is None:
            embed = discord.Embed(
                title="❓ Cible manquante",
                description=f"Utilisation: `{self.prefix}{matched.name} @membre`",
                color=discord.Color.orange(),
            )
            try:
                await message.channel.send(embed=embed, delete_after=10)
            except Exception:
                pass
            return

        # Ensure role exists
        role = await self._grant_ensure_role(message.guild, matched.role_name)
        if role is None:
            embed = discord.Embed(
                title="❌ Erreur",
                description=f"Impossible de trouver ou créer le rôle **{matched.role_name}**.",
                color=discord.Color.red(),
            )
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass
            return

        # Hierarchy check
        if role.position >= me.top_role.position:
            embed = discord.Embed(
                title="⚠️ Hiérarchie des rôles",
                description=f"Je ne peux pas gérer le rôle **{role.name}** (position trop haute). Place mon rôle au-dessus.",
                color=discord.Color.orange(),
            )
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass
            return

        # Already has role
        if role in target.roles:
            embed = discord.Embed(
                title="ℹ️ Déjà attribué",
                description=f"{target.mention} possède déjà le rôle **{role.name}**.",
                color=discord.Color.blue(),
            )
            try:
                await message.channel.send(embed=embed, delete_after=10)
            except Exception:
                pass
            return

        # Grant role
        try:
            await target.add_roles(role, reason=f"Grant command '{matched.name}' par {message.author}")
            logger.info(f"Rôle '{role.name}' attribué à {target.display_name} via commande {matched.name}.")

            embed = discord.Embed(
                title="✅ Rôle attribué",
                description=f"{target.mention} a reçu le rôle **{role.name}** !",
                color=discord.Color.green(),
            )
            embed.set_footer(text=f"Par {message.author.display_name}")
            await message.channel.send(embed=embed)

            # Send GIF if defined (path traversal protection)
            if matched.gif_path:
                resolved = os.path.realpath(matched.gif_path)
                allowed_base = os.path.realpath(".")
                if resolved.startswith(allowed_base) and os.path.isfile(resolved):
                    try:
                        await message.channel.send(file=discord.File(resolved))
                    except Exception as e:
                        logger.debug(f"Envoi gif échoué: {e}")
                else:
                    logger.warning(f"gif_path refusé (hors répertoire ou introuvable): {matched.gif_path}")
        except Exception as e:
            logger.error(f"Échec add rôle {role.name} via grant: {e}")
            embed = discord.Embed(
                title="❌ Erreur",
                description=f"Impossible d'attribuer le rôle: {e}",
                color=discord.Color.red(),
            )
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass


register(GrantCommandsFeature())
