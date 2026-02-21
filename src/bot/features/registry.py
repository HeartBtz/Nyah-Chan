"""Feature registry — discovery, ordering and dispatch."""
from __future__ import annotations

import logging
import traceback
from typing import List, Protocol

import discord

logger = logging.getLogger("nyahchan.registry")


class Feature(Protocol):
    name: str

    def setup(self, client: discord.Client) -> None: ...
    async def on_message(self, message: discord.Message) -> bool | None: ...


_features: List[Feature] = []


def register(feature: Feature) -> None:
    """Register a feature (deduplicating by name)."""
    if any(f.name == feature.name for f in _features):
        logger.warning("Feature '%s' already registered — skipping", feature.name)
        return
    _features.append(feature)
    logger.debug("Registered feature: %s", feature.name)


def get_features() -> List[Feature]:
    return list(_features)


def setup_all(client: discord.Client) -> None:
    for f in _features:
        try:
            f.setup(client)
            logger.debug("Feature '%s' setup OK", f.name)
        except Exception as e:
            logger.error(
                "Feature '%s' setup failed: %s\n%s",
                f.name, e, traceback.format_exc(),
            )


def reload_all() -> None:
    """Invoke reload() on features that expose it."""
    for f in _features:
        fn = getattr(f, "reload", None)
        if callable(fn):
            try:
                fn()
                logger.info("Feature '%s' reloaded", f.name)
            except Exception as e:
                logger.error("Feature '%s' reload failed: %s", f.name, e)


async def dispatch_on_message(message: discord.Message) -> None:
    """Dispatch to every feature; a feature returning True stops the chain."""
    for f in _features:
        try:
            consumed = await f.on_message(message)
            if consumed is True:
                break
        except Exception as e:
            logger.error(
                "Feature '%s' on_message error: %s\n%s",
                f.name, e, traceback.format_exc(),
            )
