from __future__ import annotations

from typing import Awaitable, Callable, List, Protocol
import discord


class Feature(Protocol):
    name: str

    def setup(self, client: discord.Client) -> None:
        ...

    async def on_message(self, message: discord.Message) -> None:  # noqa: D401
        ...


_features: List[Feature] = []


def register(feature: Feature) -> None:
    _features.append(feature)


def setup_all(client: discord.Client) -> None:
    for f in _features:
        f.setup(client)


def reload_all() -> None:
    """Recharger la configuration de toutes les features qui exposent reload()."""
    for f in _features:
        reload_fn = getattr(f, "reload", None)
        if callable(reload_fn):
            reload_fn()


async def dispatch_on_message(message: discord.Message) -> None:
    for f in _features:
        await f.on_message(message)
