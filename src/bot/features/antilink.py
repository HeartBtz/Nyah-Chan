"""Anti-link — block URLs and Discord invites with domain whitelist."""
from __future__ import annotations

import logging
import re

import discord

from .registry import register
from ..database import get_db

logger = logging.getLogger("nyahchan.feature.antilink")

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_INVITE_RE = re.compile(
    r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)/[a-zA-Z0-9]+",
    re.IGNORECASE,
)


class AntiLinkFeature:
    name = "antilink"

    def setup(self, client: discord.Client) -> None:
        self._client = client

    async def on_message(self, message: discord.Message) -> bool | None:
        if message.author.bot or message.guild is None:
            return None

        cfg = get_db().get_guild_config(str(message.guild.id))
        if not cfg.get("antilink_enabled"):
            return None

        member = message.author
        if isinstance(member, discord.Member) and member.guild_permissions.manage_messages:
            return None

        content = message.content or ""

        block_invites = cfg.get("antilink_block_discord_invites", 1)
        whitelist_raw = cfg.get("antilink_whitelist_domains", "")
        whitelist = {d.strip().lower() for d in whitelist_raw.split(",") if d.strip()}

        reason: str | None = None

        # Check Discord invites
        if block_invites and _INVITE_RE.search(content):
            reason = "Lien d'invitation Discord interdit"

        # Check all URLs
        if reason is None:
            urls = _URL_RE.findall(content)
            for url in urls:
                # Extract domain
                try:
                    domain = url.split("//", 1)[1].split("/", 1)[0].split(":")[0].lower()
                except IndexError:
                    continue
                # Check whitelist
                if any(domain == w or domain.endswith("." + w) for w in whitelist):
                    continue
                reason = f"Lien externe interdit: `{domain}`"
                break

        if reason is None:
            return None

        logger.info("[antilink] %s: %s", message.author, reason)

        try:
            await message.delete()
        except discord.Forbidden:
            return None

        embed = discord.Embed(
            title="🔗 Anti-Lien",
            description=f"{message.author.mention}, les liens ne sont pas autorisés ici.",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Raison", value=reason, inline=False)
        try:
            await message.channel.send(embed=embed, delete_after=10)
        except Exception:
            pass

        return True


register(AntiLinkFeature())
