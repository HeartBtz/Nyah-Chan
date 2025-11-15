import os
import asyncio
import logging
from importlib import util as importlib_util
from dotenv import load_dotenv, find_dotenv
import discord

from .features import keyword_responses  # noqa: F401
from .features import role_triggers  # noqa: F401
from .features import grant_commands  # noqa: F401
from .features import ollama_qna  # noqa: F401
from .features import commands  # noqa: F401
from .features import registry as feature_registry
from .moderation import ModerationCommands


def create_client() -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True  # nécessaire pour lire le contenu des messages
    use_members_intent = os.getenv("USE_MEMBERS_INTENT", "1") not in ("0", "false", "False")
    if use_members_intent:
        intents.members = True  # Peut nécessiter activation dans le portail développeur
    client = discord.Client(intents=intents)
    return client


def setup_logging():
    """Configure basic logging.

    LOG_LEVEL (.env) peut être DEBUG, INFO, WARNING, ERROR, CRITICAL.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)  # moins de bruit


def preflight_checks() -> bool:
    """Effectue des vérifications avant de lancer le client."""
    logger = logging.getLogger("nyahchan")
    # audioop est supprimé en Python 3.13 et utilisé par discord.py pour l'audio
    if importlib_util.find_spec("audioop") is None:
        logger.warning(
            "Module 'audioop' absent. Si vous n'utilisez pas les fonctions audio, vous pouvez ignorer. "
            "Sinon installez 'audioop-lts' (déjà tenté automatiquement) ou utilisez Python 3.12."\
        )
    return True


async def async_main():
    load_dotenv(find_dotenv())
    setup_logging()
    logger = logging.getLogger("nyahchan")
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN manquant. Ajoutez-le dans .env à la racine ou exportez la variable.")
        return

    client = create_client()
    preflight_checks()

    # Commandes de modération (slash commands)
    moderation = ModerationCommands(client)
    # on stocke l'instance sur le client pour la sync dans on_ready
    setattr(client, "moderation", moderation)

    # Features sont déjà importées en haut pour pouvoir utiliser le registry
    from .features.registry import setup_all, reload_all
    from .web import set_reload_callback

    # Import and setup events after .env is loaded
    from .events.ready import setup_ready_event
    from .events.message_create import setup_message_event
    setup_ready_event(client)
    setup_message_event(client)
    setup_all(client)

    # Permettre à la WebGUI de déclencher un reload à chaud des features
    def _reload_features() -> None:
        logger = logging.getLogger("nyahchan")
        logger.info("Reload des features demandé depuis la WebGUI")
        reload_all()

    set_reload_callback(_reload_features)

    try:
        await client.start(token)
    except discord.errors.PrivilegedIntentsRequired:
        logger.error(
            "Intents privilégiés manquants. Activez dans le portail développeur Discord (Application -> Bot -> Privileged Gateway Intents):\n"
            " - Server Members Intent (si USE_MEMBERS_INTENT=1)\n"
            " - Message Content Intent (obligatoire)\n"
            "Ou définissez USE_MEMBERS_INTENT=0 pour désactiver l'intent Members si inutile."
        )
        return


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
