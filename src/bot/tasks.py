"""Background task loop — handles tempbans, reminders, scheduled messages, giveaways."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

import discord

from .database import get_db

logger = logging.getLogger("nyahchan.tasks")

_INTERVAL = 15  # seconds between checks


async def _check_tempbans(client: discord.Client) -> None:
    db = get_db()
    expired = db.get_expired_tempbans()
    for tb in expired:
        guild = client.get_guild(int(tb["guild_id"]))
        if not guild:
            db.mark_tempban_done(tb["id"])
            continue
        try:
            bans = [entry async for entry in guild.bans()]
            banned_user = next(
                (e.user for e in bans if str(e.user.id) == tb["user_id"]), None
            )
            if banned_user:
                await guild.unban(banned_user, reason="Tempban expiré")
                logger.info("[tempban] Unbanned %s from %s", tb["user_id"], guild.name)

                from .moderation import _log
                e = discord.Embed(
                    title="🔓 Tempban expiré",
                    description=f"<@{tb['user_id']}> a été débanni automatiquement.",
                    color=discord.Color.green(),
                )
                await _log(guild, client, e)
        except Exception as ex:
            logger.error("[tempban] Unban failed for %s: %s", tb["user_id"], ex)
        db.mark_tempban_done(tb["id"])


async def _check_reminders(client: discord.Client) -> None:
    db = get_db()
    due = db.get_due_reminders()
    for r in due:
        try:
            channel = client.get_channel(int(r["channel_id"]))
            if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                embed = discord.Embed(
                    title="⏰ Rappel",
                    description=f"<@{r['user_id']}> : {r['message']}",
                    color=discord.Color.blue(),
                )
                await channel.send(content=f"<@{r['user_id']}>", embed=embed)
        except Exception as e:
            logger.error("[reminder] Failed: %s", e)
        db.mark_reminder_done(r["id"])


async def _check_scheduled_messages(client: discord.Client) -> None:
    db = get_db()
    due = db.get_due_scheduled()
    for s in due:
        try:
            channel = client.get_channel(int(s["channel_id"]))
            if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(s["message"])
        except Exception as e:
            logger.error("[scheduled] Failed: %s", e)

        if s.get("recurring") and s.get("cron"):
            # Simple recurring: add the cron interval (in hours) to next_run
            try:
                hours = int(s["cron"])
                from datetime import timedelta
                next_dt = datetime.fromisoformat(s["next_run"]) + timedelta(hours=hours)
                with db._lock:
                    db._conn.execute(
                        "UPDATE scheduled_messages SET next_run = ? WHERE id = ?",
                        (next_dt.isoformat(timespec="seconds"), s["id"]),
                    )
                    db._conn.commit()
                db._cache_invalidate(f"sm:{s['guild_id']}")
            except Exception:
                db.mark_scheduled_done(s["id"])
        else:
            db.mark_scheduled_done(s["id"])


async def _check_giveaways(client: discord.Client) -> None:
    db = get_db()
    ended = db.get_ended_giveaways()
    for g in ended:
        guild = client.get_guild(int(g["guild_id"]))
        if not guild:
            db.mark_giveaway_ended(g["id"])
            continue

        channel = guild.get_channel(int(g["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            db.mark_giveaway_ended(g["id"])
            continue

        msg_id = g.get("message_id")
        if not msg_id:
            db.mark_giveaway_ended(g["id"])
            continue

        try:
            msg = await channel.fetch_message(int(msg_id))
        except Exception:
            db.mark_giveaway_ended(g["id"])
            continue

        # Get users who reacted with 🎉
        participants = []
        for reaction in msg.reactions:
            if str(reaction.emoji) == "🎉":
                async for user in reaction.users():
                    if not user.bot:
                        participants.append(user)
                break

        winner_count = min(g.get("winners", 1), len(participants))
        if winner_count <= 0:
            embed = discord.Embed(
                title="🎉 Giveaway terminé",
                description=f"**{g['prize']}**\n\nAucun participant valide !",
                color=discord.Color.red(),
            )
            try:
                await msg.edit(embed=embed)
                await channel.send("Aucun participant pour le giveaway.")
            except Exception:
                pass
        else:
            winners = random.sample(participants, winner_count)
            winner_mentions = ", ".join(w.mention for w in winners)
            embed = discord.Embed(
                title="🎉 Giveaway terminé",
                description=f"**{g['prize']}**\n\n🏆 Gagnant(s): {winner_mentions}",
                color=discord.Color.gold(),
            )
            embed.set_footer(text=f"Organisé par <@{g['host_id']}>")
            try:
                await msg.edit(embed=embed)
                await channel.send(f"🎉 Félicitations {winner_mentions} ! Vous avez gagné **{g['prize']}** !")
            except Exception:
                pass

        db.mark_giveaway_ended(g["id"])


async def task_loop(client: discord.Client) -> None:
    """Main background loop — runs every INTERVAL seconds."""
    await client.wait_until_ready()
    logger.info("Background task loop started (interval=%ds)", _INTERVAL)
    while not client.is_closed():
        try:
            await _check_tempbans(client)
            await _check_reminders(client)
            await _check_scheduled_messages(client)
            await _check_giveaways(client)
        except Exception as e:
            logger.error("Task loop error: %s", e, exc_info=True)
        await asyncio.sleep(_INTERVAL)
