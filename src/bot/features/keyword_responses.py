from __future__ import annotations

import logging
import json
import os
from typing import Dict, List

import discord

from .registry import register
from ..config.keyword_responses_store import load_keyword_responses


logger = logging.getLogger("nyahchan.feature.keyword_responses")

# Chemin du fichier de config, similaire aux autres features
CONFIG_ENV = "KEYWORD_RESPONSES_CONFIG"
DEFAULT_CONFIG_PATH = "keyword_responses.json"


class KeywordEmbedConfig:
    """Configuration d'un embed déclenché par un ou plusieurs mots-clés."""

    def __init__(
        self,
        triggers: List[str],
        title: str,
        description: str,
        color: int,
        fields: List[dict] | None = None,
        footer: str | None = None,
        image_url: str | None = None,
        thumbnail_url: str | None = None,
    ) -> None:
        self.triggers = [t.lower() for t in triggers]
        self.title = title
        self.description = description
        self.color = color
        self.fields = fields or []
        self.footer = footer
        self.image_url = image_url
        self.thumbnail_url = thumbnail_url

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.title,
            description=self.description,
            color=self.color,
        )
        for f in self.fields:
            embed.add_field(
                name=f.get("name", ""),
                value=f.get("value", ""),
                inline=f.get("inline", False),
            )
        if self.footer:
            embed.set_footer(text=self.footer)
        if self.image_url:
            embed.set_image(url=self.image_url)
        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)
        return embed


class KeywordResponsesFeature:
    name = "keyword_responses"

    def __init__(self) -> None:
        # Liste d'embeds configurables; chaque config peut avoir plusieurs triggers.
        self.configs: List[KeywordEmbedConfig] = []
        # Index rapide: mot-clé -> config
        self._trigger_index: Dict[str, KeywordEmbedConfig] = {}
    def _load_from_store(self) -> None:
        self.configs.clear()
        self._trigger_index.clear()
        path = os.getenv(CONFIG_ENV, DEFAULT_CONFIG_PATH)
        try:
            data = load_keyword_responses(path)
            embeds_data = data.get("embeds", [])
            for item in embeds_data:
                triggers = [str(t).strip() for t in item.get("triggers", []) if str(t).strip()]
                title = str(item.get("title", "")).strip()
                description = str(item.get("description", "")).strip()
                color_raw = item.get("color", "").strip() if isinstance(item.get("color"), str) else item.get("color")

                # Gestion couleur : texte ("red", "#FF0000") ou entier
                color_value: int = discord.Color.default().value
                if isinstance(color_raw, int):
                    color_value = color_raw
                elif isinstance(color_raw, str) and color_raw:
                    named = color_raw.lower()
                    named_map = {
                        "red": discord.Color.red().value,
                        "blue": discord.Color.blue().value,
                        "green": discord.Color.green().value,
                        "yellow": discord.Color.yellow().value,
                        "purple": discord.Color.purple().value,
                        "gold": discord.Color.gold().value,
                        "orange": discord.Color.orange().value,
                    }
                    if named in named_map:
                        color_value = named_map[named]
                    else:
                        try:
                            # Support basique des codes hex: "#ff0000" ou "ff0000"
                            hex_str = named.lstrip("#")
                            color_value = int(hex_str, 16)
                        except Exception:
                            color_value = discord.Color.default().value

                fields_raw = item.get("fields", []) or []
                fields: List[dict] = []
                for f_item in fields_raw:
                    try:
                        fields.append(
                            {
                                "name": str(f_item.get("name", "")),
                                "value": str(f_item.get("value", "")),
                                "inline": bool(f_item.get("inline", False)),
                            }
                        )
                    except Exception:
                        continue

                footer = item.get("footer")
                if footer is not None:
                    footer = str(footer)

                image_url = item.get("image_url")
                if image_url is not None:
                    image_url = str(image_url)

                thumbnail_url = item.get("thumbnail_url")
                if thumbnail_url is not None:
                    thumbnail_url = str(thumbnail_url)

                if triggers and title:
                    cfg = KeywordEmbedConfig(
                        triggers=triggers,
                        title=title,
                        description=description,
                        color=color_value,
                        fields=fields,
                        footer=footer,
                        image_url=image_url,
                        thumbnail_url=thumbnail_url,
                    )
                    self.configs.append(cfg)
                    for trig in cfg.triggers:
                        self._trigger_index[trig] = cfg
            logger.info(
                "KeywordResponsesFeature: %d configuration(s) chargée(s) depuis %s (%d trigger(s)).",
                len(self.configs),
                path,
                len(self._trigger_index),
            )
        except Exception as e:
            logger.error("Erreur lecture config keyword responses (%s): %s", path, e)

    def setup(self, client: discord.Client) -> None:  # noqa: D401
        self._load_from_store()

    def reload(self) -> None:
        """Recharger la configuration depuis le store JSON."""
        self._load_from_store()

    async def on_message(self, message: discord.Message) -> None:  # noqa: D401
        if message.author.bot or message.guild is None:
            return

        content = (message.content or "").lower()

        for trig, cfg in self._trigger_index.items():
            if trig in content:
                try:
                    embed = cfg.build_embed()
                    await message.channel.send(embed=embed)
                    logger.debug("Embed envoyé pour le mot-clé '%s'", trig)
                except Exception as e:
                    logger.warning("Échec de l'envoi de l'embed pour '%s': %s", trig, e)
                break


register(KeywordResponsesFeature())
