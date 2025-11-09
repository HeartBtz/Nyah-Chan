import os
import discord
import logging
from ..services.roles import assign_or_remove_role


def setup_message_event(client: discord.Client):
    @client.event
    async def on_message(message: discord.Message):
        # Ignore bots and DMs
        if message.author.bot or message.guild is None:
            return
        await assign_or_remove_role(message)

        prefix = os.getenv("PREFIX", "!")
        if not message.content.startswith(prefix):
            return

        logger = logging.getLogger("nyahchan.commands")
        cmd_body = message.content[len(prefix):].strip().lower()

        if cmd_body == "ping":
            await message.channel.send("Pong!")
            logger.debug("Commande ping exécutée.")
        elif cmd_body in ("help", "aide"):
            await message.channel.send(
                "Commandes disponibles:\n"
                f"{prefix}ping - test de réactivité\n"
                f"{prefix}help - affiche cette aide\n"
                f"Trigger rôle: '{os.getenv('TRIGGER_WORD','Miwa')}' pour ajouter, '{os.getenv('REMOVE_TRIGGER','Heart est le meilleur')}' pour retirer."
            )
            logger.debug("Commande help exécutée.")
        elif cmd_body == "roles":
            # Restreindre aux personnes ayant la permission de gérer les rôles
            if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_roles:
                roles = sorted(message.guild.roles, key=lambda r: r.position, reverse=True)  # type: ignore[union-attr]
                lines = [f"{r.position:>3} | {r.name}" for r in roles]
                # Discord limite à ~2000 chars; tronquer si nécessaire
                text = "Liste des rôles (haut -> bas):\n" + "\n".join(lines[:40])
                await message.channel.send(f"```\n{text}\n```")
                logger.debug("Commande roles exécutée.")
            else:
                await message.channel.send("Tu n'as pas la permission pour cette commande.")
