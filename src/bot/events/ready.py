import logging
import discord

logger = logging.getLogger("nyahchan.events.ready")


def setup_ready_event(client: discord.Client):
    @client.event
    async def on_ready():
        assert client.user is not None
        logger.info(f"Connecté comme {client.user} ({client.user.id})")

        # Synchroniser les commandes de modération (slash commands)
        moderation = getattr(client, "moderation", None)
        if moderation is not None:
            try:
                await moderation.sync()
            except Exception as e:
                logger.error(f"Échec de la synchronisation des commandes de modération: {e}")
