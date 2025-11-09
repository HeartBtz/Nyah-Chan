import os
import discord

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
    if TRIGGER_WORD in content:
        try:
            role = await ensure_role(guild, ROLE_NAME)
        except RuntimeError as e:
            try:
                await message.channel.send(str(e))
            except Exception:
                pass
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
        if TRIGGER_WORD in content or REMOVE_TRIGGER in content:
            try:
                await message.channel.send("Je ne peux pas gérer ce rôle (position trop haute).")
            except Exception:
                pass
        return

    member = await _resolve_member(message)
    if member is None:
        return

    # Add role scenario
    if TRIGGER_WORD in content and REMOVE_TRIGGER not in content:
        if role in member.roles:
            return
        try:
            await member.add_roles(role, reason="Trigger role assignment")
            if REACTIONS_ENABLED:
                await message.add_reaction("✅")
        except discord.Forbidden:
            try:
                await message.channel.send("Permission refusée pour ajouter le rôle.")
            except Exception:
                pass
        except discord.HTTPException as e:
            try:
                await message.channel.send(f"Erreur lors de l’attribution du rôle: {e}")
            except Exception:
                pass
        return

    # Remove role scenario
    if REMOVE_TRIGGER in content:
        if role not in member.roles:
            return
        try:
            await member.remove_roles(role, reason="Trigger role removal")
            if REACTIONS_ENABLED:
                await message.add_reaction("🗑️")
        except discord.Forbidden:
            try:
                await message.channel.send("Permission refusée pour retirer le rôle.")
            except Exception:
                pass
        except discord.HTTPException as e:
            try:
                await message.channel.send(f"Erreur lors du retrait du rôle: {e}")
            except Exception:
                pass
