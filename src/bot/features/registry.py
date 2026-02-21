from __future__ import annotations

import logging
import traceback
from typing import List, Protocol

import discord

logger = logging.getLogger("nyahchan.registry")


class Feature(Protocol):
    name: str

    def setup(self, client: discord.Client) -> None: ...
    async def on_message(self, message: discord.Message) -> None: ...


_features: List[Feature] = []


def register(feature: Feature) -> None:
    """Register a feature with the bot."""
    _features.append(feature)
    logger.debug("Registered feature: %s", feature.name)


def get_features() -> List[Feature]:
    """Return a copy of the registered features list."""
    return list(_features)


def setup_all(client: discord.Client) -> None:
    """Initialize all registered features."""
    for f in _features:
        try:
            f.setup(client)
            logger.debug("Feature '%s' setup complete", f.name)
        except Exception as e:
            logger.error("Failed to setup feature '%s': %s\n%s", f.name, e, traceback.format_exc())


def reload_all() -> None:
    """Reload configuration of all features that expose a reload() method."""
    for f in _features:
        reload_fn = getattr(f, "reload", None)
        if callable(reload_fn):
            try:
                reload_fn()
                logger.info("Feature '%s' reloaded", f.name)
            except Exception as e:
                logger.error("Failed to reload feature '%s': %s", f.name, e)


async def dispatch_on_message(message: discord.Message) -> None:
    """Dispatch a message to all registered features with error isolation."""
    for f in _features:
        try:
            await f.on_message(message)
        except Exception as e:
            logger.error(
                "Error in feature '%s' on_message: %s\n%s",
                f.name, e, traceback.format_exc(),
            )
