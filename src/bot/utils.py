"""Shared utilities for Nyah-Chan bot."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import discord

logger = logging.getLogger("nyahchan.utils")


async def ensure_role(guild: discord.Guild, role_name: str) -> Optional[discord.Role]:
    """Find a role by name or create it. Returns None on failure."""
    for r in guild.roles:
        if r.name.lower() == role_name.lower():
            return r
    try:
        role = await guild.create_role(
            name=role_name, mentionable=True, reason="Auto-created by Nyah-Chan"
        )
        me = guild.me
        if me and me.top_role and me.top_role.position > 1:
            try:
                await role.edit(
                    position=me.top_role.position - 1,
                    reason="Auto-position under bot role",
                )
            except Exception:
                pass
        return role
    except Exception as e:
        logger.warning("Cannot create role '%s': %s", role_name, e)
        return None


def word_match(trigger: str, text: str) -> bool:
    """Check if *trigger* appears as a whole word in *text* (case-insensitive)."""
    return bool(re.search(r"\b" + re.escape(trigger) + r"\b", text, re.IGNORECASE))


def format_uptime(started_at_iso: str) -> str:
    """Return a human-readable uptime string from an ISO-8601 timestamp."""
    if not started_at_iso:
        return "N/A"
    try:
        started = datetime.fromisoformat(started_at_iso)
        total = int((datetime.now(timezone.utc) - started).total_seconds())
        days, rem = divmod(total, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        parts: list[str] = []
        if days:
            parts.append(f"{days}j")
        parts.append(f"{hours}h {minutes}m {seconds}s")
        return " ".join(parts)
    except Exception:
        return "N/A"
