"""Web administration panel — Discord OAuth2, guild-aware configuration."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import aiohttp
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import get_db

logger = logging.getLogger("nyahchan.web")

# ---------------------------------------------------------------------------
# State injected by main.py
# ---------------------------------------------------------------------------
_bot_state: dict = {}


def set_bot_state(state: dict) -> None:
    global _bot_state
    _bot_state = state


# ---------------------------------------------------------------------------
# In-memory sessions  {token: {user_id, username, avatar, guilds, expires}}
# ---------------------------------------------------------------------------
_sessions: Dict[str, Dict[str, Any]] = {}
SESSION_TTL = 86400  # 24h

DISCORD_API = "https://discord.com/api/v10"
DISCORD_CDN = "https://cdn.discordapp.com"


def _session_get(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get("session")
    if not token:
        return None
    sess = _sessions.get(token)
    if not sess or sess.get("expires", 0) < time.time():
        _sessions.pop(token, None)
        return None
    return sess


def _require_auth(request: Request):
    sess = _session_get(request)
    if not sess:
        return None
    return sess


def _admin_guilds(sess: dict) -> List[dict]:
    """Guilds where user has ADMINISTRATOR and bot is present."""
    client = _bot_state.get("client")
    bot_guild_ids = {str(g.id) for g in client.guilds} if client else set()
    result = []
    for g in sess.get("guilds", []):
        perms = g.get("permissions", 0)
        if isinstance(perms, str):
            perms = int(perms)
        if not (perms & 0x8):
            continue
        if g["id"] not in bot_guild_ids:
            continue
        result.append(g)
    return result


def _selected_guild(request: Request, admin_guilds: list) -> Optional[str]:
    """Resolve selected guild from query / cookie, fallback to first admin guild."""
    gid = request.query_params.get("guild_id") or request.cookies.get("guild_id")
    ids = {g["id"] for g in admin_guilds}
    if gid and gid in ids:
        return gid
    return admin_guilds[0]["id"] if admin_guilds else None


def _avatar_url(user: dict) -> str:
    uid = user.get("id", "0")
    av = user.get("avatar")
    if av:
        ext = "gif" if av.startswith("a_") else "png"
        return f"{DISCORD_CDN}/avatars/{uid}/{av}.{ext}?size=64"
    disc = int(user.get("discriminator") or "0")
    idx = (int(uid) >> 22) % 6 if disc == 0 else disc % 5
    return f"{DISCORD_CDN}/embed/avatars/{idx}.png"


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(docs_url=None, redoc_url=None)

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app.mount("/static", StaticFiles(directory=os.path.join(_root, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_root, "templates"))


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.get("/auth/login")
async def auth_login(request: Request):
    """Show login page or redirect to Discord OAuth2."""
    # If already logged in, go to dashboard
    if _session_get(request):
        return RedirectResponse("/ui/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/auth/discord")
async def auth_discord(request: Request):
    """Redirect to Discord OAuth2 authorization."""
    client_id = os.getenv("DISCORD_CLIENT_ID", "")
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8000/auth/callback")
    if not client_id:
        return JSONResponse({"error": "DISCORD_CLIENT_ID not set"}, 500)
    params = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
    })
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}")


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = Query("")):
    if not code:
        return RedirectResponse("/auth/login")
    client_id = os.getenv("DISCORD_CLIENT_ID", "")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8000/auth/callback")
    # Exchange code for token
    async with aiohttp.ClientSession() as http:
        async with http.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status != 200:
                logger.error("OAuth token exchange failed: %s", await resp.text())
                return RedirectResponse("/auth/login")
            token_data = await resp.json()

        access_token = token_data.get("access_token", "")
        headers = {"Authorization": f"Bearer {access_token}"}

        async with http.get(f"{DISCORD_API}/users/@me", headers=headers) as resp:
            if resp.status != 200:
                return RedirectResponse("/auth/login")
            user = await resp.json()

        async with http.get(f"{DISCORD_API}/users/@me/guilds", headers=headers) as resp:
            if resp.status != 200:
                guilds = []
            else:
                guilds = await resp.json()

    session_token = secrets.token_urlsafe(48)
    _sessions[session_token] = {
        "user_id": user.get("id"),
        "username": user.get("username"),
        "global_name": user.get("global_name"),
        "discriminator": user.get("discriminator", "0"),
        "avatar": user.get("avatar"),
        "guilds": guilds,
        "expires": time.time() + SESSION_TTL,
    }
    response = RedirectResponse("/ui/dashboard", status_code=302)
    response.set_cookie("session", session_token, httponly=True, max_age=SESSION_TTL, samesite="lax")
    return response


@app.get("/auth/logout")
async def auth_logout(request: Request):
    token = request.cookies.get("session")
    if token:
        _sessions.pop(token, None)
    response = RedirectResponse("/auth/login")
    response.delete_cookie("session")
    return response


# ---------------------------------------------------------------------------
# Redirect root
# ---------------------------------------------------------------------------
@app.get("/")
async def root(request: Request):
    sess = _session_get(request)
    if sess:
        return RedirectResponse("/ui/dashboard")
    return RedirectResponse("/auth/login")


# ---------------------------------------------------------------------------
# Helper: common template context
# ---------------------------------------------------------------------------
def _ctx(request: Request, sess: dict, page: str, **extra) -> dict:
    guilds = _admin_guilds(sess)
    gid = _selected_guild(request, guilds)
    return {
        "request": request,
        "page": page,
        "user": sess,
        "avatar_url": _avatar_url(sess),
        "admin_guilds": guilds,
        "guild_id": gid,
        **extra,
    }


# ---------------------------------------------------------------------------
# UI pages
# ---------------------------------------------------------------------------
@app.get("/ui/dashboard", response_class=HTMLResponse)
async def ui_dashboard(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    from .utils import format_uptime
    ctx = _ctx(request, sess, "dashboard")
    ctx["bot_state"] = _bot_state
    ctx["uptime"] = format_uptime(_bot_state.get("started_at", ""))
    ctx["warning_count"] = get_db().total_warning_count()
    resp = templates.TemplateResponse("dashboard.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/keywords", response_class=HTMLResponse)
async def ui_keywords(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "keywords")
    resp = templates.TemplateResponse("keywords.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/roles", response_class=HTMLResponse)
async def ui_roles(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "roles")
    resp = templates.TemplateResponse("roles.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/grant", response_class=HTMLResponse)
async def ui_grant(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "grant")
    resp = templates.TemplateResponse("grant.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/warnings", response_class=HTMLResponse)
async def ui_warnings(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "warnings")
    resp = templates.TemplateResponse("warnings.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/settings", response_class=HTMLResponse)
async def ui_settings(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "settings")
    resp = templates.TemplateResponse("settings.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


# ---------- New UI pages ----------
@app.get("/ui/custom-commands", response_class=HTMLResponse)
async def ui_custom_commands(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "custom_commands")
    resp = templates.TemplateResponse("custom_commands.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/reaction-roles", response_class=HTMLResponse)
async def ui_reaction_roles(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "reaction_roles")
    resp = templates.TemplateResponse("reaction_roles.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/scheduled", response_class=HTMLResponse)
async def ui_scheduled(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "scheduled")
    resp = templates.TemplateResponse("scheduled.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/xp", response_class=HTMLResponse)
async def ui_xp(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "xp")
    resp = templates.TemplateResponse("xp.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


@app.get("/ui/audit-log", response_class=HTMLResponse)
async def ui_audit_log(request: Request):
    sess = _require_auth(request)
    if not sess:
        return RedirectResponse("/auth/login")
    ctx = _ctx(request, sess, "audit_log")
    resp = templates.TemplateResponse("audit_log.html", ctx)
    if ctx["guild_id"]:
        resp.set_cookie("guild_id", ctx["guild_id"], max_age=SESSION_TTL, samesite="lax")
    return resp


# ---------------------------------------------------------------------------
# API: health (public)
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def api_health():
    return {
        "status": "ok",
        "ready": _bot_state.get("ready", False),
        "guilds": _bot_state.get("guilds", 0),
        "users": _bot_state.get("users", 0),
    }


# ---------------------------------------------------------------------------
# API auth guard
# ---------------------------------------------------------------------------
def _api_auth(request: Request) -> Optional[dict]:
    sess = _session_get(request)
    if not sess:
        return None
    return sess


def _api_guild(request: Request, sess: dict) -> Optional[str]:
    gid = request.query_params.get("guild_id") or request.cookies.get("guild_id")
    if not gid:
        return None
    admin_ids = {g["id"] for g in _admin_guilds(sess)}
    if gid not in admin_ids:
        return None
    return gid


# ---------------------------------------------------------------------------
# API: guild list
# ---------------------------------------------------------------------------
@app.get("/api/guilds")
async def api_guilds(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    guilds = _admin_guilds(sess)
    return [{"id": g["id"], "name": g["name"], "icon": g.get("icon")} for g in guilds]


# ---------------------------------------------------------------------------
# API: guild config / settings
# ---------------------------------------------------------------------------
@app.get("/api/settings")
async def api_settings_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    cfg = get_db().get_guild_config(gid)
    escalation = get_db().get_escalation_rules(gid)
    return {"config": cfg, "escalation": escalation}


@app.post("/api/settings")
async def api_settings_post(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    body = await request.json()
    config = body.get("config", {})
    escalation = body.get("escalation")
    if config:
        get_db().save_guild_config(gid, **config)
    if escalation is not None:
        get_db().save_escalation_rules(gid, escalation)
    _audit(request, sess, gid, "settings", "Updated guild settings")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: keywords
# ---------------------------------------------------------------------------
@app.get("/api/keywords")
async def api_keywords_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_keywords(gid)


@app.post("/api/keywords")
async def api_keywords_post(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    data = await request.json()
    get_db().save_keywords(gid, data if isinstance(data, list) else [])
    _audit(request, sess, gid, "keywords", "Saved keyword responses")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: role triggers
# ---------------------------------------------------------------------------
@app.get("/api/roles")
async def api_roles_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_role_triggers(gid)


@app.post("/api/roles")
async def api_roles_post(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    data = await request.json()
    get_db().save_role_triggers(gid, data if isinstance(data, list) else [])
    _audit(request, sess, gid, "roles", "Saved role triggers")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: grant commands
# ---------------------------------------------------------------------------
@app.get("/api/grant")
async def api_grant_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_grant_commands(gid)


@app.post("/api/grant")
async def api_grant_post(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    data = await request.json()
    get_db().save_grant_commands(gid, data if isinstance(data, list) else [])
    _audit(request, sess, gid, "grant", "Saved grant commands")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: warnings
# ---------------------------------------------------------------------------
@app.get("/api/warnings")
async def api_warnings_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_warnings(gid)


@app.delete("/api/warnings/{wid}")
async def api_warning_delete(request: Request, wid: int):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    ok = get_db().remove_warning(gid, wid)
    return {"ok": ok}


# ---------------------------------------------------------------------------
# API: bot stats
# ---------------------------------------------------------------------------
@app.get("/api/stats")
async def api_stats(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    from .utils import format_uptime
    return {
        "ready": _bot_state.get("ready", False),
        "guilds": _bot_state.get("guilds", 0),
        "users": _bot_state.get("users", 0),
        "uptime": format_uptime(_bot_state.get("started_at", "")),
        "warnings": get_db().total_warning_count(),
    }


# ---------------------------------------------------------------------------
# API: custom commands
# ---------------------------------------------------------------------------
@app.get("/api/custom-commands")
async def api_custom_commands_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_custom_commands(gid)


@app.post("/api/custom-commands")
async def api_custom_commands_post(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    data = await request.json()
    get_db().save_custom_commands(gid, data if isinstance(data, list) else [])
    _audit(request, sess, gid, "custom_commands", "Saved custom commands")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: reaction roles
# ---------------------------------------------------------------------------
@app.get("/api/reaction-roles")
async def api_reaction_roles_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_reaction_roles(gid)


@app.post("/api/reaction-roles")
async def api_reaction_roles_post(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    data = await request.json()
    get_db().save_reaction_roles(gid, data if isinstance(data, list) else [])
    _audit(request, sess, gid, "reaction_roles", "Saved reaction roles")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: scheduled messages
# ---------------------------------------------------------------------------
@app.get("/api/scheduled")
async def api_scheduled_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_scheduled_messages(gid)


@app.post("/api/scheduled")
async def api_scheduled_post(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    data = await request.json()
    get_db().save_scheduled_messages(gid, data if isinstance(data, list) else [])
    _audit(request, sess, gid, "scheduled_messages", "Saved scheduled messages")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: XP role rewards
# ---------------------------------------------------------------------------
@app.get("/api/xp-rewards")
async def api_xp_rewards_get(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_xp_role_rewards(gid)


@app.post("/api/xp-rewards")
async def api_xp_rewards_post(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    data = await request.json()
    get_db().save_xp_role_rewards(gid, data if isinstance(data, list) else [])
    _audit(request, sess, gid, "xp_rewards", "Saved XP rewards")
    return {"ok": True}


@app.get("/api/xp-leaderboard")
async def api_xp_leaderboard(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_xp_leaderboard(gid, 50)


# ---------------------------------------------------------------------------
# API: activity stats (charts)
# ---------------------------------------------------------------------------
@app.get("/api/activity")
async def api_activity(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    days = int(request.query_params.get("days", "30"))
    return get_db().get_activity_stats(gid, days)


# ---------------------------------------------------------------------------
# API: audit log (WebUI)
# ---------------------------------------------------------------------------
@app.get("/api/audit-log")
async def api_audit_log(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    return get_db().get_audit_logs(gid, 200)


# ---------------------------------------------------------------------------
# API: config backup (export / import)
# ---------------------------------------------------------------------------
@app.get("/api/backup/export")
async def api_backup_export(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    _audit(request, sess, gid, "backup_export", "Exported config backup")
    return get_db().export_guild_config(gid)


@app.post("/api/backup/import")
async def api_backup_import(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    data = await request.json()
    get_db().import_guild_config(gid, data)
    _audit(request, sess, gid, "backup_import", "Imported config backup")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: guild roles (for role management)
# ---------------------------------------------------------------------------
@app.get("/api/guild-roles")
async def api_guild_roles(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    client = _bot_state.get("client")
    if not client:
        return JSONResponse({"error": "bot offline"}, 503)
    guild = client.get_guild(int(gid))
    if not guild:
        return JSONResponse({"error": "guild not found"}, 404)
    roles = []
    for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
        if r.is_default():
            continue
        roles.append({
            "id": str(r.id), "name": r.name, "color": str(r.color),
            "position": r.position, "members": len(r.members),
        })
    return roles


@app.get("/api/guild-members")
async def api_guild_members(request: Request):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    client = _bot_state.get("client")
    if not client:
        return JSONResponse({"error": "bot offline"}, 503)
    guild = client.get_guild(int(gid))
    if not guild:
        return JSONResponse({"error": "guild not found"}, 404)
    search = (request.query_params.get("search") or "").lower()
    members = []
    for m in guild.members:
        if m.bot:
            continue
        if search and search not in m.name.lower() and search not in (m.nick or "").lower():
            continue
        members.append({
            "id": str(m.id), "name": str(m), "nick": m.nick,
            "avatar": m.display_avatar.url,
            "roles": [str(r.id) for r in m.roles if not r.is_default()],
        })
        if len(members) >= 100:
            break
    return members


@app.post("/api/guild-members/{mid}/roles")
async def api_member_roles(request: Request, mid: str):
    sess = _api_auth(request)
    if not sess:
        return JSONResponse({"error": "unauthorized"}, 401)
    gid = _api_guild(request, sess)
    if not gid:
        return JSONResponse({"error": "no guild"}, 400)
    client = _bot_state.get("client")
    if not client:
        return JSONResponse({"error": "bot offline"}, 503)
    guild = client.get_guild(int(gid))
    if not guild:
        return JSONResponse({"error": "guild not found"}, 404)
    member = guild.get_member(int(mid))
    if not member:
        return JSONResponse({"error": "member not found"}, 404)
    body = await request.json()
    add_roles = body.get("add", [])
    remove_roles = body.get("remove", [])
    me = guild.me
    for rid in add_roles:
        role = guild.get_role(int(rid))
        if role and role.position < me.top_role.position and role not in member.roles:
            try:
                await member.add_roles(role, reason=f"WebUI by {sess.get('username')}")
            except Exception:
                pass
    for rid in remove_roles:
        role = guild.get_role(int(rid))
        if role and role.position < me.top_role.position and role in member.roles:
            try:
                await member.remove_roles(role, reason=f"WebUI by {sess.get('username')}")
            except Exception:
                pass
    _audit(request, sess, gid, "role_manage", f"Modified roles for {mid}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------
def _audit(request: Request, sess: dict, gid: str, action: str, detail: str = "") -> None:
    try:
        get_db().add_audit_log(
            gid, sess.get("user_id", ""), sess.get("username", ""),
            action, detail,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
async def start_web_app(host: str = "0.0.0.0", port: int = 8000) -> None:
    config = uvicorn.Config(
        app, host=host, port=port,
        log_level="info", access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("Web panel starting on http://%s:%d", host, port)
    await server.serve()
