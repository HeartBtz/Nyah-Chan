from __future__ import annotations

import os
import logging
import asyncio
import time
import aiohttp
import discord
from .registry import register

logger = logging.getLogger("nyahchan.feature.ollama")


class OllamaQnAFeature:
    name = "ollama_qna"

    def __init__(self) -> None:
        self.enabled: bool = False
        self.base_url: str | None = None
        self.model: str | None = None
        self.timeout: int | None = None
        self.system_prompt: str | None = None
        self.prefix = os.getenv("PREFIX", "!")
        self.max_chunk = 1900  # keep some margin under Discord 2000 char limit
        self._rate_limits: dict[str, float] = {}  # user_id -> last_query_timestamp
        self._session: aiohttp.ClientSession | None = None

    def setup(self, client: discord.Client) -> None:  # noqa: D401
        # Décide ici, après que .env ait été chargé dans main.async_main()
        self.enabled = os.getenv("OLLAMA_ENABLED", "0").strip() == "1"
        if not self.enabled:
            logger.info(f"[ollama] Désactivé (OLLAMA_ENABLED={os.getenv('OLLAMA_ENABLED')!r})")
            return

        # Charger la configuration depuis l'environnement
        self.base_url = os.getenv("OLLAMA_BASE_URL")
        self.model = os.getenv("OLLAMA_MODEL")
        timeout_raw = os.getenv("OLLAMA_TIMEOUT")

        if not self.base_url or not self.model or timeout_raw is None:
            logger.error(
                "[ollama] Activé dans .env mais configuration incomplète: "
                f"OLLAMA_BASE_URL={self.base_url!r}, OLLAMA_MODEL={self.model!r}, OLLAMA_TIMEOUT={timeout_raw!r}. "
                "Désactivation de la feature."
            )
            self.enabled = False
            return

        try:
            self.timeout = int(timeout_raw)
        except ValueError:
            logger.error(f"[ollama] OLLAMA_TIMEOUT invalide: {timeout_raw!r}. Désactivation de la feature.")
            self.enabled = False
            return

        self.system_prompt = os.getenv("OLLAMA_SYSTEM_PROMPT", "").strip() or None

        # Create a reusable aiohttp session
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )

        logger.info(
            f"[ollama] Activé | base_url={self.base_url} | model={self.model} | "
            f"timeout={self.timeout}s | system_prompt={'yes' if self.system_prompt else 'no'}"
        )

    async def _query_ollama(self, prompt: str) -> str:
        # Use /api/generate endpoint (simpler, stateless)
        url = f"{self.base_url.rstrip('/')}/api/generate"
        payload: dict = {"model": self.model, "prompt": prompt, "stream": False}
        if self.system_prompt:
            payload["system"] = self.system_prompt
        try:
            start = time.perf_counter()
            logger.debug(f"[ollama] POST {url} model={self.model} prompt_len={len(prompt)}")
            session = self._session or aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
            async with session.post(url, json=payload) as resp:
                dur = (time.perf_counter() - start) * 1000
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"[ollama] HTTP {resp.status} en {dur:.0f}ms: {text[:200]}")
                    return f"Erreur Ollama ({resp.status}): {text[:500]}"
                data = await resp.json()
                answer = str(data.get("response", "(Réponse vide)")).strip()
                logger.debug(f"[ollama] Réponse OK en {dur:.0f}ms, len={len(answer)}")
                return answer
        except asyncio.TimeoutError:
            logger.warning("[ollama] Timeout de la requête")
            return "(Timeout de la requête Ollama)"
        except Exception as e:
            logger.error(f"[ollama] Exception requête: {e}")
            return f"(Erreur Ollama: {e})"

    async def on_message(self, message: discord.Message) -> None:  # noqa: D401
        if not self.enabled:
            return
        if message.author.bot or message.guild is None:
            return
        # Trigger: bot mention + un point d'interrogation dans le contenu
        if not message.mentions:
            return
        bot_user = message.guild.me
        if bot_user is None or bot_user not in message.mentions:
            return
        content = (message.content or "").strip()
        # Remove mention markup from prompt
        cleaned = content.replace(f"<@{bot_user.id}>", "").replace(f"<@!{bot_user.id}>", "").strip()
        if not cleaned:
            return
        if '?' not in cleaned:
            return  # Simple heuristic: only answer questions

        # Rate limiting: 1 query per user per 15 seconds
        now = time.time()
        user_key = str(message.author.id)

        # Periodic cleanup of stale rate-limit entries
        if len(self._rate_limits) > 500:
            cutoff = now - 30
            self._rate_limits = {k: v for k, v in self._rate_limits.items() if v > cutoff}

        last_query = self._rate_limits.get(user_key, 0)
        if now - last_query < 15:
            remaining = int(15 - (now - last_query))
            try:
                await message.channel.send(
                    f"⏳ Patiente encore {remaining}s avant de poser une autre question.",
                    delete_after=5,
                )
            except Exception:
                pass
            return
        self._rate_limits[user_key] = now

        logger.info(
            "[ollama] Trigger par %s in guild=%s channel=%s prompt='%s'",
            message.author.id, message.guild.id, message.channel.id,
            cleaned[:120] + ('...' if len(cleaned) > 120 else ''),
        )
        await self._answer(message, cleaned)

    async def _answer(self, message: discord.Message, prompt: str) -> None:
        # Show typing indicator while querying
        async with message.channel.typing():
            answer = await self._query_ollama(prompt)

        # Send as embed for cleaner presentation
        if len(answer) <= 4000:
            embed = discord.Embed(
                description=answer,
                color=discord.Color.blurple(),
            )
            embed.set_author(name=f"Réponse pour {message.author.display_name}", icon_url=message.author.display_avatar.url if message.author.display_avatar else None)
            embed.set_footer(text=f"Modèle: {self.model}")
            try:
                await message.reply(embed=embed, mention_author=False)
            except Exception as e:
                logger.debug(f"Échec envoi embed réponse Ollama: {e}")
        else:
            # Long response: chunk as plain text
            chunks = self._chunk(answer)
            logger.debug(f"[ollama] Envoi réponse en {len(chunks)} chunk(s)")
            for idx, ch in enumerate(chunks, start=1):
                header = f"(part {idx}/{len(chunks)})\n" if len(chunks) > 1 else ""
                out = header + ch
                try:
                    await message.channel.send(out)
                except Exception as e:
                    logger.debug(f"Échec envoi chunk réponse Ollama: {e}")
                    break

    def _chunk(self, text: str) -> list[str]:
        if len(text) <= self.max_chunk:
            return [text]
        parts = []
        start = 0
        while start < len(text):
            end = start + self.max_chunk
            parts.append(text[start:end])
            start = end
        return parts


register(OllamaQnAFeature())
