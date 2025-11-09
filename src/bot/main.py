import os
import asyncio
from dotenv import load_dotenv, find_dotenv
import discord


def create_client() -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True  # nécessaire pour lire le contenu des messages
    use_members_intent = os.getenv("USE_MEMBERS_INTENT", "1") not in ("0", "false", "False")
    if use_members_intent:
        intents.members = True  # Peut nécessiter activation dans le portail développeur
    client = discord.Client(intents=intents)
    return client


async def async_main():
    load_dotenv(find_dotenv())
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN manquant. Ajoutez-le dans un fichier .env à la racine de python_miwa_bot/ ou exportez la variable d'environnement.")
        return

    client = create_client()

    # Import and setup events after .env is loaded
    from .events.ready import setup_ready_event
    from .events.message_create import setup_message_event
    setup_ready_event(client)
    setup_message_event(client)

    try:
        await client.start(token)
    except discord.errors.PrivilegedIntentsRequired:
        print("[ERREUR] Intents privilégiés manquants.\n" \
              "Activez dans le portail développeur Discord (Application -> Bot -> Privileged Gateway Intents):\n" \
              " - Server Members Intent (si USE_MEMBERS_INTENT=1)\n" \
              " - Message Content Intent (obligatoire pour détecter le mot déclencheur)\n" \
              "Ou définissez USE_MEMBERS_INTENT=0 dans votre .env pour désactiver l'intent Members si vous n'en avez pas strictement besoin.")
        return


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
