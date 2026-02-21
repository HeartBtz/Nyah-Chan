"""Slash commands — moderation, info, and utilities."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import List, Optional

import discord
from discord import app_commands

from .database import get_db

logger = logging.getLogger("nyahchan.moderation")


def _label(user: discord.abc.User) -> str:
    return f"{user} (`{user.id}`)"


def _log_channel(guild: discord.Guild, client: discord.Client):
    cfg = get_db().get_guild_config(str(guild.id))
    raw = cfg.get("mod_log_channel_id")
    if not raw:
        return None
    try:
        ch = guild.get_channel(int(raw)) or client.get_channel(int(raw))
    except (ValueError, TypeError):
        return None
    if isinstance(ch, (discord.TextChannel, discord.Thread)):
        return ch
    return None


async def _log(guild, client, embed):
    ch = _log_channel(guild, client)
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception:
            pass


class ModerationCommands:
    def __init__(self, client: discord.Client) -> None:
        self.client = client
        self.tree = app_commands.CommandTree(client)
        self._register_commands()
        self._register_error_handler()

    def _register_error_handler(self) -> None:
        @self.tree.error
        async def on_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            if isinstance(error, app_commands.MissingPermissions):
                msg = f"🚫 Permission(s) manquante(s): `{', '.join(error.missing_permissions)}`"
            elif isinstance(error, app_commands.BotMissingPermissions):
                msg = f"🚫 Je n'ai pas les permissions: `{', '.join(error.missing_permissions)}`"
            elif isinstance(error, app_commands.CommandOnCooldown):
                msg = f"⏳ Cooldown. Réessaie dans {error.retry_after:.1f}s."
            else:
                msg = f"❌ Erreur: {error}"
                logger.error("Slash error: %s", error, exc_info=error)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _register_commands(self) -> None:

        # ---------- /userinfo ----------
        @self.tree.command(name="userinfo", description="Infos sur un utilisateur")
        async def userinfo(interaction: discord.Interaction, member: Optional[discord.Member] = None):
            t = member or interaction.user
            embed = discord.Embed(title=f"Infos — {t}", color=discord.Color.blurple())
            embed.set_thumbnail(url=t.display_avatar.url)
            embed.add_field(name="ID", value=f"`{t.id}`", inline=True)
            embed.add_field(name="Créé", value=discord.utils.format_dt(t.created_at, "R"), inline=True)
            if isinstance(t, discord.Member):
                embed.add_field(name="Rejoint", value=discord.utils.format_dt(t.joined_at, "R") if t.joined_at else "?", inline=True)
                roles = [r.mention for r in t.roles if not r.is_default()][:20]
                embed.add_field(name=f"Rôles [{len(roles)}]", value=", ".join(roles) or "Aucun", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ---------- /avatar ----------
        @self.tree.command(name="avatar", description="Avatar d'un utilisateur")
        async def avatar(interaction: discord.Interaction, member: Optional[discord.Member] = None):
            t = member or interaction.user
            embed = discord.Embed(title=f"Avatar de {t}", color=discord.Color.blurple())
            embed.set_image(url=t.display_avatar.with_size(1024).url)
            await interaction.response.send_message(embed=embed)

        # ---------- /serverinfo ----------
        @self.tree.command(name="serverinfo", description="Infos du serveur")
        async def serverinfo(interaction: discord.Interaction):
            g = interaction.guild
            if not g:
                return await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            embed = discord.Embed(title=f"📊 {g.name}", color=discord.Color.blurple())
            if g.icon:
                embed.set_thumbnail(url=g.icon.url)
            embed.add_field(name="Propriétaire", value=str(g.owner) if g.owner else "?", inline=True)
            embed.add_field(name="Membres", value=str(g.member_count or 0), inline=True)
            embed.add_field(name="Rôles", value=str(len(g.roles)), inline=True)
            embed.add_field(name="Salons texte", value=str(len(g.text_channels)), inline=True)
            embed.add_field(name="Salons vocaux", value=str(len(g.voice_channels)), inline=True)
            embed.add_field(name="Boosts", value=str(g.premium_subscription_count), inline=True)
            embed.add_field(name="Créé le", value=discord.utils.format_dt(g.created_at, "F"), inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ---------- /purge ----------
        @self.tree.command(name="purge", description="Supprimer des messages en masse")
        @app_commands.checks.has_permissions(manage_messages=True)
        async def purge(interaction: discord.Interaction, count: app_commands.Range[int, 1, 200]):
            if not isinstance(interaction.channel, discord.TextChannel):
                return await interaction.response.send_message("Salon texte uniquement.", ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            deleted = await interaction.channel.purge(limit=count)
            await interaction.followup.send(f"🗑️ {len(deleted)} message(s) supprimé(s).", ephemeral=True)
            e = discord.Embed(title="🗑️ Purge", description=f"{len(deleted)} messages dans {interaction.channel.mention}", color=discord.Color.orange())
            e.add_field(name="Modérateur", value=_label(interaction.user), inline=False)
            await _log(interaction.guild, self.client, e)

        # ---------- /ban ----------
        @self.tree.command(name="ban", description="Bannir un membre")
        @app_commands.checks.has_permissions(ban_members=True)
        async def ban(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
            if not interaction.guild:
                return await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            if member == interaction.user:
                return await interaction.response.send_message("Tu ne peux pas te bannir.", ephemeral=True)
            if member.top_role >= interaction.guild.me.top_role:
                return await interaction.response.send_message("Hiérarchie de rôles insuffisante.", ephemeral=True)
            r = reason or "Aucune raison."
            await interaction.response.defer()
            try:
                await member.send(f"Banni de **{interaction.guild.name}**: {r}")
            except Exception:
                pass
            try:
                await interaction.guild.ban(member, reason=r)
                e = discord.Embed(title="🚫 Ban", description=f"{member.mention} banni.", color=discord.Color.red())
            except Exception as ex:
                e = discord.Embed(title="🚫 Ban — Échec", description=str(ex), color=discord.Color.red())
            e.add_field(name="Modérateur", value=_label(interaction.user), inline=False)
            e.add_field(name="Raison", value=r, inline=False)
            await interaction.followup.send(embed=e)
            await _log(interaction.guild, self.client, e)

        # ---------- /kick ----------
        @self.tree.command(name="kick", description="Expulser un membre")
        @app_commands.checks.has_permissions(kick_members=True)
        async def kick(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
            if not interaction.guild:
                return await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            if member == interaction.user:
                return await interaction.response.send_message("Tu ne peux pas te kick.", ephemeral=True)
            if member.top_role >= interaction.guild.me.top_role:
                return await interaction.response.send_message("Hiérarchie de rôles insuffisante.", ephemeral=True)
            r = reason or "Aucune raison."
            await interaction.response.defer()
            try:
                await member.send(f"Expulsé de **{interaction.guild.name}**: {r}")
            except Exception:
                pass
            try:
                await interaction.guild.kick(member, reason=r)
                e = discord.Embed(title="🚪 Kick", description=f"{member.mention} expulsé.", color=discord.Color.orange())
            except Exception as ex:
                e = discord.Embed(title="🚪 Kick — Échec", description=str(ex), color=discord.Color.orange())
            e.add_field(name="Modérateur", value=_label(interaction.user), inline=False)
            e.add_field(name="Raison", value=r, inline=False)
            await interaction.followup.send(embed=e)
            await _log(interaction.guild, self.client, e)

        # ---------- /timeout ----------
        @self.tree.command(name="timeout", description="Timeout un membre")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def timeout(interaction: discord.Interaction, member: discord.Member,
                          minutes: app_commands.Range[int, 1, 43200], reason: Optional[str] = None):
            if not interaction.guild:
                return await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            if member == interaction.user:
                return await interaction.response.send_message("Tu ne peux pas te timeout.", ephemeral=True)
            if member.top_role >= interaction.guild.me.top_role:
                return await interaction.response.send_message("Hiérarchie insuffisante.", ephemeral=True)
            r = reason or "Aucune raison."
            until = discord.utils.utcnow() + timedelta(minutes=minutes)
            await interaction.response.defer()
            try:
                await member.send(f"Timeout {minutes}min sur **{interaction.guild.name}**: {r}")
            except Exception:
                pass
            try:
                await member.timeout(until, reason=r)
                e = discord.Embed(title="⏱ Timeout", description=f"{member.mention} — {minutes}min.", color=discord.Color.blurple())
            except Exception as ex:
                e = discord.Embed(title="⏱ Timeout — Échec", description=str(ex), color=discord.Color.blurple())
            e.add_field(name="Modérateur", value=_label(interaction.user), inline=False)
            e.add_field(name="Raison", value=r, inline=False)
            await interaction.followup.send(embed=e)
            await _log(interaction.guild, self.client, e)

        # ---------- /warn ----------
        @self.tree.command(name="warn", description="Avertir un membre")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warn(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
            if not interaction.guild:
                return await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            if member == interaction.user:
                return await interaction.response.send_message("Tu ne peux pas te warn.", ephemeral=True)
            r = reason or "Aucune raison."
            db = get_db()
            gid = str(interaction.guild.id)
            entry = db.add_warning(gid, str(member.id), str(interaction.user.id), r)
            total = db.get_warning_count(gid, str(member.id))
            e = discord.Embed(title="⚠️ Avertissement", description=f"{member.mention} averti.", color=discord.Color.yellow())
            e.add_field(name="ID", value=f"`#{entry['id']}`", inline=True)
            e.add_field(name="Modérateur", value=_label(interaction.user), inline=False)
            e.add_field(name="Raison", value=r, inline=False)
            e.set_footer(text=f"Total: {total}")
            await interaction.response.send_message(embed=e)
            await _log(interaction.guild, self.client, e)
            # escalation
            await self._escalate(interaction, member, total)

        # ---------- /warnings ----------
        @self.tree.command(name="warnings", description="Lister les avertissements")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def warnings_cmd(interaction: discord.Interaction, member: discord.Member):
            if not interaction.guild:
                return await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            w = get_db().get_warnings(str(interaction.guild.id), str(member.id))
            if not w:
                return await interaction.response.send_message(f"{member.mention} n'a aucun avertissement.", ephemeral=True)
            embed = discord.Embed(title=f"📋 Warnings — {member}", description=f"{len(w)} avertissement(s)", color=discord.Color.yellow())
            for wi in w[:10]:
                embed.add_field(name=f"#{wi['id']}", value=f"Mod: <@{wi['moderator_id']}>\n{wi['reason']}\n{wi['created_at']}", inline=False)
            if len(w) > 10:
                embed.set_footer(text=f"Affichage 10/{len(w)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ---------- /unwarn ----------
        @self.tree.command(name="unwarn", description="Supprimer un avertissement")
        @app_commands.checks.has_permissions(moderate_members=True)
        async def unwarn(interaction: discord.Interaction, member: discord.Member, warning_id: int):
            if not interaction.guild:
                return await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            ok = get_db().remove_warning(str(interaction.guild.id), warning_id)
            if ok:
                await interaction.response.send_message(f"✅ Warning `#{warning_id}` supprimé.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Aucun warning `#{warning_id}` trouvé.", ephemeral=True)

    # ------------------------------------------------------------------
    # Escalation
    # ------------------------------------------------------------------
    async def _escalate(self, interaction: discord.Interaction, member: discord.Member, total: int) -> None:
        if not interaction.guild:
            return
        rules = get_db().get_escalation_rules(str(interaction.guild.id))
        hit = next((r for r in rules if r["warn_count"] == total), None)
        if not hit:
            return
        action = hit["action"]
        param = hit.get("action_param", 0)
        me = interaction.guild.me
        if me is None or member.top_role >= me.top_role:
            return
        e = discord.Embed(color=discord.Color.dark_red())
        e.add_field(name="Warnings", value=str(total), inline=True)
        try:
            if action == "timeout":
                until = discord.utils.utcnow() + timedelta(minutes=param)
                await member.timeout(until, reason=f"Auto-escalation: {total} warns")
                e.title = "⏱ Auto-Timeout"
                e.description = f"{member.mention} — {param}min (auto)"
            elif action == "kick":
                await interaction.guild.kick(member, reason=f"Auto-escalation: {total} warns")
                e.title = "🚪 Auto-Kick"
                e.description = f"{member.mention} expulsé (auto)"
            elif action == "ban":
                await interaction.guild.ban(member, reason=f"Auto-escalation: {total} warns")
                e.title = "🚫 Auto-Ban"
                e.description = f"{member.mention} banni (auto)"
            else:
                return
            await interaction.followup.send(embed=e)
            await _log(interaction.guild, self.client, e)
        except Exception as ex:
            logger.error("Escalation %s failed: %s", action, ex)

    # ------------------------------------------------------------------
    async def sync(self) -> None:
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d slash command(s).", len(synced))
        except Exception as e:
            logger.error("Slash sync failed: %s", e)
