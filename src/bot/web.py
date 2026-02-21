from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Cookie, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config.grant_commands_store import load_grant_commands, save_grant_commands
from .config.keyword_responses_store import load_keyword_responses, save_keyword_responses
from .config.role_triggers_store import load_role_triggers, save_role_triggers
from .moderation_store import WarningStore
from .utils import calculate_uptime

logger = logging.getLogger("nyahchan.web")

_reload_callback = None
_bot_state: Dict[str, Any] = {}

# Simple session store (in-memory)
_sessions: Dict[str, float] = {}  # token -> expiry timestamp
SESSION_DURATION = 24 * 3600  # 24h


def set_reload_callback(callback) -> None:
    """Register a callback for hot-reloading bot features."""
    global _reload_callback
    _reload_callback = callback


def set_bot_state(state: Dict[str, Any]) -> None:
    """Register the bot state dict for dashboard access."""
    global _bot_state
    _bot_state = state


def _get_secret_key() -> str:
    key = os.getenv("WEB_SECRET_KEY", "").strip()
    if not key:
        logger.error("WEB_SECRET_KEY non défini dans .env — l'admin panel ne sera pas accessible.")
        return secrets.token_urlsafe(64)  # Random unreachable key as safe fallback
    return key


def _create_session() -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_DURATION
    # Clean expired sessions
    now = time.time()
    expired = [k for k, v in _sessions.items() if v < now]
    for k in expired:
        del _sessions[k]
    return token


def _validate_session(token: Optional[str]) -> bool:
    """Check if a session token is valid."""
    if not token:
        return False
    expiry = _sessions.get(token)
    if expiry is None or expiry < time.time():
        _sessions.pop(token, None)
        return False
    return True


# --- FastAPI App ---
app = FastAPI(title="Nyah-Chan Admin", docs_url=None, redoc_url=None)

# Static files
static_dir = Path(__file__).resolve().parent.parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates
templates_dir = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


# --- Auth middleware ---
def _require_auth(session_token: Optional[str]) -> None:
    """Raise redirect if not authenticated."""
    if not _validate_session(session_token):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


# --- Login ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "") -> Any:
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error}
    )


@app.post("/login")
async def login_submit(request: Request) -> Any:
    form = await request.form()
    password = str(form.get("password", ""))
    secret = _get_secret_key()

    if hmac.compare_digest(password, secret):
        token = _create_session()
        response = RedirectResponse(url="/ui/dashboard", status_code=303)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=SESSION_DURATION,
        )
        logger.info("Web admin login successful from %s", request.client.host if request.client else "unknown")
        return response
    else:
        logger.warning("Failed login attempt from %s", request.client.host if request.client else "unknown")
        return RedirectResponse(url="/login?error=Mot+de+passe+incorrect", status_code=303)


@app.get("/logout")
async def logout(session: Optional[str] = Cookie(None)) -> Any:
    if session:
        _sessions.pop(session, None)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


# --- Dashboard ---
@app.get("/", response_class=HTMLResponse)
async def index(session: Optional[str] = Cookie(None)) -> Any:
    if _validate_session(session):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/ui/dashboard", response_class=HTMLResponse)
async def ui_dashboard(request: Request, session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)

    # Gather stats
    keywords_data = load_keyword_responses()
    roles_data = load_role_triggers()
    grant_data = load_grant_commands()

    stats = {
        "bot_ready": _bot_state.get("ready", False),
        "guilds": _bot_state.get("guilds", 0),
        "users": _bot_state.get("users", 0),
        "started_at": _bot_state.get("started_at", ""),
        "keywords_count": len(keywords_data.get("embeds", [])),
        "triggers_count": len(roles_data.get("triggers", [])),
        "grant_count": len(grant_data.get("commands", [])),
        "warnings_count": WarningStore().get_total_count(),
    }

    # Calculate uptime
    stats["uptime"] = calculate_uptime(stats["started_at"])

    # Client latency
    client = _bot_state.get("client")
    stats["latency"] = f"{round(client.latency * 1000)}ms" if client else "N/A"

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats, "active": "dashboard"},
    )


# --- UI Pages ---
@app.get("/ui/keywords", response_class=HTMLResponse)
async def ui_keywords(request: Request, session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    data = load_keyword_responses()
    return templates.TemplateResponse(
        "keywords.html",
        {"request": request, "embeds": data.get("embeds", []), "active": "keywords"},
    )


@app.get("/ui/roles", response_class=HTMLResponse)
async def ui_roles(request: Request, session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    data = load_role_triggers()
    return templates.TemplateResponse(
        "roles.html",
        {"request": request, "triggers": data.get("triggers", []), "active": "roles"},
    )


@app.get("/ui/grant", response_class=HTMLResponse)
async def ui_grant(request: Request, session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    data = load_grant_commands()
    return templates.TemplateResponse(
        "grant.html",
        {"request": request, "commands": data.get("commands", []), "active": "grant"},
    )


# --- Warnings page ---
@app.get("/ui/warnings", response_class=HTMLResponse)
async def ui_warnings(request: Request, session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    store = WarningStore()
    # Collect warnings from all guilds
    all_warnings = []
    for gkey in store._data:
        all_warnings.extend(store.get_all_warnings_for_guild(int(gkey)))
    return templates.TemplateResponse(
        "warnings.html",
        {"request": request, "warnings": all_warnings, "active": "warnings"},
    )


@app.get("/api/warnings", response_class=JSONResponse)
async def api_get_warnings(session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    store = WarningStore()
    all_warnings = []
    for gkey in store._data:
        for w in store.get_all_warnings_for_guild(int(gkey)):
            all_warnings.append({
                "id": w.id,
                "user_id": str(w.user_id),
                "moderator_id": str(w.moderator_id),
                "guild_id": str(w.guild_id),
                "reason": w.reason,
                "created_at": w.created_at,
            })
    all_warnings.sort(key=lambda x: x["id"], reverse=True)
    return {"warnings": all_warnings}


# --- API: Health check (public) ---
@app.get("/api/health", response_class=JSONResponse)
async def api_health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "bot_ready": _bot_state.get("ready", False),
        "guilds": _bot_state.get("guilds", 0),
    }


# --- API: Keyword responses ---
@app.get("/api/keywords", response_class=JSONResponse)
async def api_get_keywords(session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    return load_keyword_responses()


@app.post("/api/keywords", response_class=JSONResponse)
async def api_save_keywords(request: Request, session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    payload = await request.json()
    embeds = payload.get("embeds", [])
    if not isinstance(embeds, list):
        return {"ok": False, "error": "'embeds' must be a list"}
    # Sanitize data
    for embed in embeds:
        if not isinstance(embed, dict):
            return {"ok": False, "error": "Each embed must be an object"}
    logger.info("Saving %d keyword response(s)", len(embeds))
    save_keyword_responses({"embeds": embeds})
    return {"ok": True}


# --- API: Role triggers ---
@app.get("/api/roles", response_class=JSONResponse)
async def api_get_roles(session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    return load_role_triggers()


@app.post("/api/roles", response_class=JSONResponse)
async def api_save_roles(request: Request, session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    payload = await request.json()
    triggers = payload.get("triggers", [])
    if not isinstance(triggers, list):
        return {"ok": False, "error": "'triggers' must be a list"}
    logger.info("Saving %d role trigger(s)", len(triggers))
    save_role_triggers({"triggers": triggers})
    return {"ok": True}


# --- API: Grant commands ---
@app.get("/api/grant", response_class=JSONResponse)
async def api_get_grant(session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    return load_grant_commands()


@app.post("/api/grant", response_class=JSONResponse)
async def api_save_grant(request: Request, session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    payload = await request.json()
    commands = payload.get("commands", [])
    if not isinstance(commands, list):
        return {"ok": False, "error": "'commands' must be a list"}
    logger.info("Saving %d grant command(s)", len(commands))
    save_grant_commands({"commands": commands})
    return {"ok": True}


# --- API: Reload ---
@app.post("/api/reload", response_class=JSONResponse)
async def api_reload(session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    if _reload_callback is None:
        return {"ok": False, "error": "reload callback not configured"}
    try:
        _reload_callback()
        logger.info("Feature reload triggered via API")
        return {"ok": True}
    except Exception as e:
        logger.error("Reload error: %s", e)
        return {"ok": False, "error": str(e)}


# --- API: Bot stats (for dashboard auto-refresh) ---
@app.get("/api/stats", response_class=JSONResponse)
async def api_stats(session: Optional[str] = Cookie(None)) -> Any:
    _require_auth(session)
    client = _bot_state.get("client")
    started_at = _bot_state.get("started_at", "")
    uptime = calculate_uptime(started_at)

    return {
        "bot_ready": _bot_state.get("ready", False),
        "guilds": _bot_state.get("guilds", 0),
        "users": _bot_state.get("users", 0),
        "uptime": uptime,
        "latency": f"{round(client.latency * 1000)}ms" if client else "N/A",
    }


# --- Start ---
async def start_web_app(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    logger.info("Starting Nyah-Chan Admin on http://%s:%d", host, port)
    await server.serve()
