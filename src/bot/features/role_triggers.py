from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import List

import discord

from .registry import register

logger = logging.getLogger("nyahchan.feature.roles")


def _get_config_path() -> str:
    """Get config path at runtime (after .env is loaded), not import time."""
    return os.getenv("ROLE_TRIGGERS_CONFIG", "role_triggers.json")


@dataclass
class RoleTrigger:
    trigger: str
    role_name: str
    remove_trigger: str | None = None


class RoleTriggersFeature:
    name = "role_triggers"

    def __init__(self) -> None:
        self.triggers: List[RoleTrigger] = []
        self.reactions_enabled: bool = True

    def _load_from_config(self) -> None:
        self.triggers.clear()
        self.reactions_enabled = os.getenv("REACTIONS_ENABLED", "1") not in ("0", "false", "False")
        config_path = _get_config_path()

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("triggers", []):
                    trigger = str(item.get("trigger", "")).strip().lower()
                    role_name = str(item.get("role_name", "")).strip()
                    remove_raw = item.get("remove_trigger")
                    remove_trigger = str(remove_raw).strip().lower() if remove_raw else None

                    if trigger and role_name:
                        self.triggers.append(RoleTrigger(trigger, role_name, remove_trigger))
                logger.info("Loaded %d role trigger(s) from %s", len(self.triggers), config_path)
            except Exception as e:
                logger.error("Error reading role triggers config: %s", e)

        # Fallback to env variables if no config
        if not self.triggers:
            env_trigger = os.getenv("TRIGGER_WORD")
            env_role = os.getenv("ROLE_NAME")
            env_remove = os.getenv("REMOVE_TRIGGER")
            if env_trigger and env_role:
                self.triggers.append(
                    RoleTrigger(
                        env_trigger.lower(),
                        env_role,
                        env_remove.lower() if env_remove else None,
                    )
                )
                logger.info("Loaded role trigger from environment variables (fallback)")

    def setup(self, client: discord.Client) -> None:
        self._load_from_config()

    def reload(self) -> None:
        """Reload triggers from config."""
        self._load_from_config()

    async def _ensure_role(self, guild: discord.Guild, role_name: str) -> discord.Role | None:
        """Find or create a role by name."""
        for r in guild.roles:
            if r.name.lower() == role_name.lower():
                return r
        try:
            role = await guild.create_role(
                name=role_name, mentionable=True, reason="Auto-created for role trigger"
            )
            me = guild.me
            if me and me.top_role and me.top_role.position > 1:
                target_pos = me.top_role.position - 1
                try:
                    await role.edit(position=target_pos, reason="Auto-position under bot role")
                except Exception:
                    pass
            return role
        except Exception as e:
            logger.warning("Cannot create role '%s': %s", role_name, e)
            return None

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if not self.triggers:
            return

        content = (message.content or "").lower()
        guild = message.guild
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return

        for rt in self.triggers:
            trigger_hit = rt.trigger in content
            remove_hit = bool(rt.remove_trigger and rt.remove_trigger in content)

            if not trigger_hit and not remove_hit:
                continue

            role = await self._ensure_role(guild, rt.role_name)
            if role is None:
                continue
            if role.position >= me.top_role.position:
                logger.warning(
                    "Role '%s' too high (pos=%d >= bot pos=%d)",
                    role.name, role.position, me.top_role.position,
                )
                continue

            member = message.author if isinstance(message.author, discord.Member) else None
            if member is None:
                try:
                    member = await guild.fetch_member(message.author.id)
                except Exception:
                    continue

            # Add role
            if trigger_hit and not remove_hit:
                if role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Trigger '{rt.trigger}'")
                        if self.reactions_enabled:
                            try:
                                await message.add_reaction("✅")
                            except Exception:
                                pass
                        logger.info("Role '%s' added to %s via '%s'", role.name, member, rt.trigger)
                    except Exception as e:
                        logger.error("Failed to add role %s: %s", role.name, e)

            # Remove role
            if remove_hit:
                if role in member.roles:
                    try:
                        await member.remove_roles(role, reason=f"Remove trigger '{rt.remove_trigger}'")
                        if self.reactions_enabled:
                            try:
                                await message.add_reaction("🗑️")
                            except Exception:
                                pass
                        logger.info("Role '%s' removed from %s via '%s'", role.name, member, rt.remove_trigger)
                    except Exception as e:
                        logger.error("Failed to remove role %s: %s", role.name, e)


register(RoleTriggersFeature())
