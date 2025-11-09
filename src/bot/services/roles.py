import os
import discord
import logging

ROLE_NAME = os.getenv("ROLE_NAME", "Miwa")
TRIGGER_WORD = os.getenv("TRIGGER_WORD", "Miwa").lower()
REMOVE_TRIGGER = os.getenv("REMOVE_TRIGGER", "heart est le meilleur").lower()
REACTIONS_ENABLED = os.getenv("REACTIONS_ENABLED", "1") not in ("0", "false", "False")


async def ensure_role(guild: discord.Guild, role_name: str) -> discord.Role:
    # Try cache first
    for role in guild.roles:
        if role.name == role_name:
            return role
    # Create role
    try:
        role = await guild.create_role(name=role_name, mentionable=True, reason="Création auto pour trigger")
        # Tenter de placer le rôle juste sous le rôle le plus haut du bot pour éviter les soucis de hiérarchie
        me = guild.me
        logger = logging.getLogger("nyahchan.roles")
        if me and me.top_role and me.top_role.position > 1:
            target_pos = me.top_role.position - 1
            try:
                await role.edit(position=target_pos, reason="Auto-reposition sous le top rôle du bot")
                logger.debug(f"Rôle repositionné à {target_pos} sous le top rôle du bot.")
            except Exception as e:
                logger.debug(f"Impossible de repositionner le rôle automatiquement: {e}")
        return role
    except discord.Forbidden:
        raise RuntimeError("Permissions insuffisantes pour créer le rôle.")
    except discord.HTTPException as e:
        raise RuntimeError(f"Erreur HTTP lors de la création du rôle: {e}")


async def _resolve_member(message: discord.Message) -> discord.Member | None:
    if isinstance(message.author, discord.Member):
        return message.author
    try:
        return await message.guild.fetch_member(message.author.id)  # type: ignore[arg-type]
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


async def assign_or_remove_role(message: discord.Message):
    content = (message.content or "").lower()
    guild = message.guild
    if guild is None:
        return

    # Bot member
    me = guild.me
    if me is None:
        return

    # Ensure permission early
    if not me.guild_permissions.manage_roles:
        if TRIGGER_WORD in content or REMOVE_TRIGGER in content:
            try:
                await message.channel.send("Je n’ai pas la permission de gérer les rôles.")
            except Exception:
                pass
        return

    # Ensure role exists if we'll need to add it
    role: discord.Role | None = None
    logger = logging.getLogger("nyahchan.roles")

    if TRIGGER_WORD in content:
        try:
            role = await ensure_role(guild, ROLE_NAME)
            logger.debug(f"Rôle obtenu/créé: {role.name} (id={role.id})")
        except RuntimeError as e:
            try:
                await message.channel.send(str(e))
            except Exception:
                pass
            logger.warning(f"Échec création rôle: {e}")
            return
    else:
        # If removing only, locate role if exists
        for r in guild.roles:
            if r.name == ROLE_NAME:
                role = r
                break
        if role is None and REMOVE_TRIGGER in content:
            # Nothing to remove
            return

    if role is None:
        return

    # Check position (bot must be higher)
    if role.position >= me.top_role.position:
        logger.warning(
            f"Hiérarchie insuffisante: role '{role.name}' pos={role.position} >= bot top '{me.top_role.name}' pos={me.top_role.position}"
        )
        if TRIGGER_WORD in content or REMOVE_TRIGGER in content:
            try:
                await message.channel.send(
                    f"Je ne peux pas gérer le rôle '{role.name}' (position trop haute).\n"
                    f"Place mon rôle '{me.top_role.name}' au-dessus de '{role.name}' dans Paramètres du serveur → Rôles."
                )
            except Exception:
                pass
        return

    member = await _resolve_member(message)
    if member is None:
        return

    # Add role scenario
    if TRIGGER_WORD in content and REMOVE_TRIGGER not in content:
        if role in member.roles:
            logger.debug("Rôle déjà présent sur le membre, rien à faire.")
            return
        try:
            await member.add_roles(role, reason="Trigger role assignment")
            if REACTIONS_ENABLED:
                await message.add_reaction("✅")
            logger.info(f"Rôle '{role.name}' attribué à {member.display_name} ({member.id}) via trigger.")
        except discord.Forbidden:
            try:
                await message.channel.send("Permission refusée pour ajouter le rôle.")
            except Exception:
                pass
            logger.error("Forbidden lors de l'ajout du rôle.")
        except discord.HTTPException as e:
            try:
                await message.channel.send(f"Erreur lors de l’attribution du rôle: {e}")
            except Exception:
                pass
            logger.error(f"HTTPException add_roles: {e}")
        return

    # Remove role scenario
    if REMOVE_TRIGGER in content:
        if role not in member.roles:
            logger.debug("Rôle absent du membre lors de la demande de retrait, rien à faire.")
            return
        try:
            await member.remove_roles(role, reason="Trigger role removal")
            if REACTIONS_ENABLED:
                await message.add_reaction("🗑️")
            logger.info(f"Rôle '{role.name}' retiré de {member.display_name} ({member.id}) via trigger.")
        except discord.Forbidden:
            try:
                await message.channel.send("Permission refusée pour retirer le rôle.")
            except Exception:
                pass
            logger.error("Forbidden lors du retrait du rôle.")
        except discord.HTTPException as e:
            try:
                await message.channel.send(f"Erreur lors du retrait du rôle: {e}")
            except Exception:
                pass
            logger.error(f"HTTPException remove_roles: {e}")
