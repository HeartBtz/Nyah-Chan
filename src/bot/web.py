from __future__ import annotations

import asyncio
from typing import Any, Dict
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config.keyword_responses_store import (
    load_keyword_responses,
    save_keyword_responses,
)
from .config.role_triggers_store import (
    load_role_triggers,
    save_role_triggers,
)
from .config.grant_commands_store import (
    load_grant_commands,
    save_grant_commands,
)


logger = logging.getLogger("nyahchan.web")


app = FastAPI(title="Nyah-Chan Admin")

# Static & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------- UI PAGES ----------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Any:
    logger.info("HTTP GET / -> redirect /ui/keywords")
    return RedirectResponse(url="/ui/keywords", status_code=302)


@app.get("/ui/keywords", response_class=HTMLResponse)
async def ui_keywords(request: Request) -> Any:
    logger.debug("Rendering /ui/keywords")
    data = load_keyword_responses()
    return templates.TemplateResponse(
        "keywords.html",
        {"request": request, "embeds": data.get("embeds", [])},
    )


@app.get("/ui/roles", response_class=HTMLResponse)
async def ui_roles(request: Request) -> Any:
    logger.debug("Rendering /ui/roles")
    data = load_role_triggers()
    return templates.TemplateResponse(
        "roles.html",
        {"request": request, "triggers": data.get("triggers", [])},
    )


@app.get("/ui/grant", response_class=HTMLResponse)
async def ui_grant(request: Request) -> Any:
    logger.debug("Rendering /ui/grant")
    data = load_grant_commands()
    return templates.TemplateResponse(
        "grant.html",
        {"request": request, "commands": data.get("commands", [])},
    )


# ---------- API: KEYWORD RESPONSES ----------


@app.get("/api/keywords", response_class=JSONResponse)
async def api_get_keywords() -> Dict[str, Any]:
    logger.debug("GET /api/keywords")
    return load_keyword_responses()


@app.post("/api/keywords", response_class=JSONResponse)
async def api_save_keywords(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Simple validation: ensure "embeds" is a list
    embeds = payload.get("embeds", [])
    if not isinstance(embeds, list):
        logger.warning("Invalid payload on /api/keywords: 'embeds' n'est pas une liste")
        return {"ok": False, "error": "'embeds' doit être une liste"}
    logger.info("Saving keyword responses (%d embeds)", len(embeds))
    save_keyword_responses({"embeds": embeds})
    return {"ok": True}


# ---------- API: ROLE TRIGGERS ----------


@app.get("/api/roles", response_class=JSONResponse)
async def api_get_roles() -> Dict[str, Any]:
    logger.debug("GET /api/roles")
    return load_role_triggers()


@app.post("/api/roles", response_class=JSONResponse)
async def api_save_roles(payload: Dict[str, Any]) -> Dict[str, Any]:
    triggers = payload.get("triggers", [])
    if not isinstance(triggers, list):
        logger.warning("Invalid payload on /api/roles: 'triggers' n'est pas une liste")
        return {"ok": False, "error": "'triggers' doit être une liste"}
    logger.info("Saving role triggers (%d triggers)", len(triggers))
    save_role_triggers({"triggers": triggers})
    return {"ok": True}


# ---------- API: GRANT COMMANDS ----------


@app.get("/api/grant", response_class=JSONResponse)
async def api_get_grant() -> Dict[str, Any]:
    logger.debug("GET /api/grant")
    return load_grant_commands()


@app.post("/api/grant", response_class=JSONResponse)
async def api_save_grant(payload: Dict[str, Any]) -> Dict[str, Any]:
    commands = payload.get("commands", [])
    if not isinstance(commands, list):
        logger.warning("Invalid payload on /api/grant: 'commands' n'est pas une liste")
        return {"ok": False, "error": "'commands' doit être une liste"}
    logger.info("Saving grant commands (%d commands)", len(commands))
    save_grant_commands({"commands": commands})
    return {"ok": True}


# Helper pour lancer FastAPI avec Uvicorn à partir d'une boucle existante


async def start_web_app(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    logger.info("Starting Nyah-Chan Admin GUI on http://%s:%d", host, port)
    await server.serve()
