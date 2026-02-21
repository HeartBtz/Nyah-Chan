"""Auto-moderation feature for Nyah-Chan.

Enforces rules configured via .env:
- AUTOMOD_BAD_WORDS: comma-separated banned words
- AUTOMOD_MAX_MENTIONS: max mentions per message (default 5)
- AUTOMOD_MAX_CAPS_PERCENT: max CAPS percentage (default 80, min 10 chars)
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Dict, List, Set

import discord

from .registry import register

logger = logging.getLogger("nyahchan.feature.automod")

# Minimum message length before caps check is applied
_MIN_CAPS_LENGTH = 10


class AutoModerationFeature:
    name = "automod"

    def __init__(self) -> None:
        self.enabled: bool = False
        self.bad_words: Set[str] = set()
        self.max_mentions: int = 5
        self.max_caps_percent: int = 80
        # Track violations for progressive response
        self._violations: Dict[int, List[float]] = {}  # user_id -> [timestamps]

    def setup(self, client: discord.Client) -> None:
        self.enabled = os.getenv("AUTOMOD_ENABLED", "0").strip() == "1"
        if not self.enabled:
            logger.info("[automod] Disabled (AUTOMOD_ENABLED=%r)", os.getenv("AUTOMOD_ENABLED"))
            return

        raw_words = os.getenv("AUTOMOD_BAD_WORDS", "")
        self.bad_words = {w.strip().lower() for w in raw_words.split(",") if w.strip()}

        try:
            self.max_mentions = int(os.getenv("AUTOMOD_MAX_MENTIONS", "5"))
        except ValueError:
            self.max_mentions = 5

        try:
            self.max_caps_percent = int(os.getenv("AUTOMOD_MAX_CAPS_PERCENT", "80"))
        except ValueError:
            self.max_caps_percent = 80

        logger.info(
            "[automod] Enabled | bad_words=%d | max_mentions=%d | max_caps=%d%%",
            len(self.bad_words), self.max_mentions, self.max_caps_percent,
        )

    def reload(self) -> None:
        """Reload automod config from env."""
        # Re-read from env (dotenv reloaded by bot)
        raw_words = os.getenv("AUTOMOD_BAD_WORDS", "")
        self.bad_words = {w.strip().lower() for w in raw_words.split(",") if w.strip()}
        try:
            self.max_mentions = int(os.getenv("AUTOMOD_MAX_MENTIONS", "5"))
        except ValueError:
            self.max_mentions = 5
        try:
            self.max_caps_percent = int(os.getenv("AUTOMOD_MAX_CAPS_PERCENT", "80"))
        except ValueError:
            self.max_caps_percent = 80
        logger.info("[automod] Config reloaded")

    def _record_violation(self, user_id: int) -> int:
        """Record a violation and return the count in the last 10 minutes."""
        now = time.time()
        history = self._violations.setdefault(user_id, [])
        history.append(now)
        # Keep only last 10 minutes
        cutoff = now - 600
        history[:] = [t for t in history if t > cutoff]
        return len(history)

    def _check_bad_words(self, content: str) -> str | None:
        """Return the matched bad word or None."""
        lower = content.lower()
        for word in self.bad_words:
            if re.search(r"\b" + re.escape(word) + r"\b", lower):
                return word
        return None

    def _check_mentions(self, message: discord.Message) -> bool:
        """Return True if too many mentions."""
        total = len(message.mentions) + len(message.role_mentions)
        return total > self.max_mentions

    def _check_caps(self, content: str) -> bool:
        """Return True if message is excessively ALL CAPS."""
        alpha = [c for c in content if c.isalpha()]
        if len(alpha) < _MIN_CAPS_LENGTH:
            return False
        upper_count = sum(1 for c in alpha if c.isupper())
        percent = (upper_count / len(alpha)) * 100
        return percent > self.max_caps_percent

    async def on_message(self, message: discord.Message) -> None:
        if not self.enabled:
            return
        if message.author.bot or message.guild is None:
            return

        # Skip members with manage_messages (mods are exempt)
        member = message.author
        if isinstance(member, discord.Member) and member.guild_permissions.manage_messages:
            return

        content = message.content or ""
        reason: str | None = None
        violation_type: str | None = None

        # Check bad words
        if self.bad_words:
            matched = self._check_bad_words(content)
            if matched:
                reason = f"Mot interdit détecté: ||{matched}||"
                violation_type = "bad_word"

        # Check mention spam
        if reason is None and self._check_mentions(message):
            reason = f"Trop de mentions ({len(message.mentions) + len(message.role_mentions)} > {self.max_mentions})"
            violation_type = "mention_spam"

        # Check excessive caps
        if reason is None and self._check_caps(content):
            reason = "Message en MAJUSCULES excessives"
            violation_type = "caps"

        if reason is None:
            return

        # --- Take action ---
        count = self._record_violation(message.author.id)
        logger.info(
            "[automod] Violation #%d by %s (%s): %s",
            count, message.author, violation_type, reason,
        )

        # Delete the offending message
        try:
            await message.delete()
        except discord.Forbidden:
            logger.warning("[automod] Cannot delete message — missing permissions")
            return
        except Exception as e:
            logger.error("[automod] Error deleting message: %s", e)
            return

        # Send warning embed
        embed = discord.Embed(
            title="🛡️ Auto-Modération",
            description=f"{message.author.mention}, ton message a été supprimé.",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Raison", value=reason, inline=False)

        if count >= 5:
            embed.add_field(
                name="⚠️ Attention",
                value=f"Tu as {count} violations en 10 minutes. Un modérateur pourrait intervenir.",
                inline=False,
            )
        elif count >= 3:
            embed.add_field(
                name="Avertissement",
                value=f"C'est ta {count}e violation récente. Merci de respecter les règles.",
                inline=False,
            )

        embed.set_footer(text="Auto-modération Nyah-Chan")

        try:
            await message.channel.send(embed=embed, delete_after=15)
        except Exception:
            pass

        # Periodic cleanup
        if len(self._violations) > 1000:
            cutoff = time.time() - 600
            self._violations = {
                uid: ts for uid, ts in self._violations.items()
                if any(t > cutoff for t in ts)
            }


register(AutoModerationFeature())
