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


async def dispatch_on_message(message: discord.Message) -> None:
    for f in _features:
        await f.on_message(message)
