from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass
from typing import List, Optional

import discord

from .registry import register

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
        # Charger depuis JSON si présent (par défaut: grant_commands.json à la racine)
        path = os.getenv(CONFIG_ENV, "grant_commands.json")
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
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

        # Fallback .env simple: un seul mapping
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

    async def _ensure_role(self, guild: discord.Guild, role_name: str) -> Optional[discord.Role]:
        for r in guild.roles:
            if r.name == role_name:
                return r
        try:
            role = await guild.create_role(name=role_name, mentionable=True, reason="Création auto via grant command")
            # auto position sous le top rôle du bot si possible
            me = guild.me
            if me and me.top_role and me.top_role.position > 1:
                target_pos = me.top_role.position - 1
                try:
                    await role.edit(position=target_pos, reason="Auto-reposition sous top rôle du bot")
                except Exception:
                    pass
            return role
        except Exception as e:
            logger.error(f"Impossible de créer le rôle '{role_name}': {e}")
            return None

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

        # Extraire nom de commande
        body = content[len(self.prefix):].strip()
        cmd = body.split()[0].lower() if body else ""
        if not cmd:
            return

        # Correspondance commande
        matched: Optional[GrantCommand] = None
        for gc in self.commands:
            if gc.name == cmd:
                matched = gc
                break
        if matched is None:
            return

        # Vérifier permissions d'appelant
        if message.author.id not in matched.allowed_user_ids:
            return

        # Trouver la cible
        target = self._parse_target_member(message)
        if target is None:
            try:
                await message.channel.send("Spécifie une cible: ex. !{0} @membre".format(matched.name))
            except Exception:
                pass
            return

        # Assurer le rôle
        role = await self._ensure_role(message.guild, matched.role_name)
        if role is None:
            return

        # Vérifier hiérarchie
        if role.position >= me.top_role.position:
            try:
                await message.channel.send(
                    f"Je ne peux pas gérer le rôle '{role.name}' (position trop haute). Place mon rôle au-dessus."
                )
            except Exception:
                pass
            return

        # Attribuer
        if role in target.roles:
            # déjà présent, rien à faire
            return
        try:
            await target.add_roles(role, reason=f"Grant command '{matched.name}' par {message.author}")
            logger.info(f"Rôle '{role.name}' attribué à {target.display_name} via commande {matched.name}.")
            # Envoyer le GIF si défini
            if matched.gif_path:
                # Préserver relative path depuis racine projet
                if os.path.exists(matched.gif_path):
                    try:
                        await message.channel.send(file=discord.File(matched.gif_path))
                    except Exception as e:
                        logger.debug(f"Envoi gif échoué: {e}")
                else:
                    logger.debug(f"gif_path introuvable: {matched.gif_path}")
        except Exception as e:
            logger.error(f"Échec add rôle {role.name} via grant: {e}")


register(GrantCommandsFeature())
