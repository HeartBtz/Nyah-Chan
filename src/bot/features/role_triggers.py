from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass
from typing import List
import discord

from .registry import register

logger = logging.getLogger("nyahchan.feature.roles")

CONFIG_PATH = os.getenv("ROLE_TRIGGERS_CONFIG", "role_triggers.json")


@dataclass
class RoleTrigger:
    trigger: str
    role_name: str
    remove_trigger: str | None = None


class RoleTriggersFeature:
    name = "role_triggers"

    def __init__(self) -> None:
        self.triggers: List[RoleTrigger] = []
        self.reactions_enabled = os.getenv("REACTIONS_ENABLED", "1") not in ("0", "false", "False")
    def _load_from_config(self) -> None:
        self.triggers.clear()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("triggers", []):
                    rt = RoleTrigger(
                        trigger=str(item.get("trigger", "")).lower(),
                        role_name=str(item.get("role_name", "")).strip(),
                        remove_trigger=(str(item.get("remove_trigger")) if item.get("remove_trigger") else None)
                    )
                    if rt.trigger and rt.role_name:
                        self.triggers.append(rt)
                logger.info(f"Chargement {len(self.triggers)} trigger(s) de rôles depuis {CONFIG_PATH}.")
            except Exception as e:
                logger.error(f"Erreur lecture config role triggers: {e}")

        # Backward compatibility environnement si aucune config
        if not self.triggers:
            env_trigger = os.getenv("TRIGGER_WORD")
            env_role = os.getenv("ROLE_NAME")
            env_remove = os.getenv("REMOVE_TRIGGER")
            if env_trigger and env_role:
                self.triggers.append(RoleTrigger(env_trigger.lower(), env_role, env_remove.lower() if env_remove else None))
                logger.info("Fallback sur variables d'environnement pour triggers de rôles.")

    def setup(self, client: discord.Client) -> None:  # noqa: D401
        self._load_from_config()

    def reload(self) -> None:
        """Recharger la configuration des triggers depuis le JSON/env."""
        self._load_from_config()

    async def _ensure_role(self, guild: discord.Guild, role_name: str) -> discord.Role | None:
        for r in guild.roles:
            if r.name == role_name:
                return r
        try:
            role = await guild.create_role(name=role_name, mentionable=True, reason="Création auto pour trigger")
            # Tentative reposition
            me = guild.me
            if me and me.top_role and me.top_role.position > 1:
                target_pos = me.top_role.position - 1
                try:
                    await role.edit(position=target_pos, reason="Auto-reposition sous le top rôle du bot")
                except Exception:
                    pass
            return role
        except Exception as e:
            logger.warning(f"Impossible de créer le rôle {role_name}: {e}")
            return None

    async def on_message(self, message: discord.Message) -> None:  # noqa: D401
        if message.author.bot or message.guild is None:
            return
        content = (message.content or "").lower()
        guild = message.guild
        me = guild.me
        if me is None:
            return
        if not me.guild_permissions.manage_roles:
            return

        for rt in self.triggers:
            trigger_hit = rt.trigger in content
            remove_hit = rt.remove_trigger and rt.remove_trigger.lower() in content
            if not trigger_hit and not remove_hit:
                continue

            role = await self._ensure_role(guild, rt.role_name)
            if role is None:
                continue
            if role.position >= me.top_role.position:
                logger.warning(f"Rôle '{role.name}' trop haut (pos={role.position} >= bot pos={me.top_role.position}).")
                continue

            member = message.author if isinstance(message.author, discord.Member) else None
            if member is None:
                try:
                    member = await guild.fetch_member(message.author.id)  # type: ignore[arg-type]
                except Exception:
                    continue

            # Add
            if trigger_hit and (not remove_hit):
                if role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Trigger '{rt.trigger}'")
                        if self.reactions_enabled:
                            try:
                                await message.add_reaction("✅")
                            except Exception:
                                pass
                        logger.info(f"Rôle '{role.name}' attribué à {member.display_name} via '{rt.trigger}'.")
                    except Exception as e:
                        logger.error(f"Échec add rôle {role.name}: {e}")
            # Remove
            if remove_hit:
                if role in member.roles:
                    try:
                        await member.remove_roles(role, reason=f"Remove trigger '{rt.remove_trigger}'")
                        if self.reactions_enabled:
                            try:
                                await message.add_reaction("🗑️")
                            except Exception:
                                pass
                        logger.info(f"Rôle '{role.name}' retiré de {member.display_name} via '{rt.remove_trigger}'.")
                    except Exception as e:
                        logger.error(f"Échec remove rôle {role.name}: {e}")


register(RoleTriggersFeature())
