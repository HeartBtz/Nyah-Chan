from __future__ import annotations

import json
import os
from typing import Any, Dict


DEFAULT_GRANT_COMMANDS_PATH = "grant_commands.json"
GRANT_COMMANDS_ENV = "GRANT_COMMANDS_CONFIG"


def get_grant_commands_path() -> str:
    return os.getenv(GRANT_COMMANDS_ENV, DEFAULT_GRANT_COMMANDS_PATH)


def load_grant_commands(path: str | None = None) -> Dict[str, Any]:
    if path is None:
        path = get_grant_commands_path()
    if not path:
        return {"commands": []}
    if not os.path.exists(path):
        # If the file does not exist yet, create it with an empty structure
        data: Dict[str, Any] = {"commands": []}
        save_grant_commands(data, path)
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"commands": []}
        data.setdefault("commands", [])
        return data
    except Exception:
        return {"commands": []}


def save_grant_commands(data: Dict[str, Any], path: str | None = None) -> None:
    if path is None:
        path = get_grant_commands_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
