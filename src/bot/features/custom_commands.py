"""Custom commands — user-defined text/embed responses via WebUI."""
from __future__ import annotations

import logging

import discord

from .registry import register
from ..database import get_db

logger = logging.getLogger("nyahchan.feature.custom_commands")


def _parse_color(raw: str) -> int:
    raw = raw.strip().lower()
    named = {"red": 0xe74c3c, "blue": 0x3498db, "green": 0x2ecc71,
             "yellow": 0xf1c40f, "purple": 0x9b59b6, "orange": 0xe67e22}
    if raw in named:
        return named[raw]
    try:
        return int(raw.lstrip("#"), 16)
    except Exception:
        return discord.Color.blurple().value


class CustomCommandsFeature:
    name = "custom_commands"

    def setup(self, client: discord.Client) -> None:
        pass

    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        gid = str(message.guild.id)
        cfg = get_db().get_guild_config(gid)
        prefix = cfg.get("prefix", "!")
        content = message.content or ""
        if not content.startswith(prefix):
            return None

        body = content[len(prefix):].strip()
        cmd = body.split()[0].lower() if body else ""
        if not cmd:
            return None

        commands = get_db().get_custom_commands(gid)
        matched = next((c for c in commands if c.get("name", "").lower() == cmd), None)
        if matched is None:
            return None

        response = matched.get("response", "")
        use_embed = matched.get("embed", 0)

        if use_embed:
            color = _parse_color(matched.get("color", ""))
            embed = discord.Embed(description=response, color=color)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(response)

        return None


register(CustomCommandsFeature())
