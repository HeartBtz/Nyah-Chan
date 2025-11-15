from __future__ import annotations

import json
import os
from typing import Any, Dict


DEFAULT_ROLE_TRIGGERS_PATH = "role_triggers.json"
ROLE_TRIGGERS_ENV = "ROLE_TRIGGERS_CONFIG"


def get_role_triggers_path() -> str:
    return os.getenv(ROLE_TRIGGERS_ENV, DEFAULT_ROLE_TRIGGERS_PATH)


def load_role_triggers(path: str | None = None) -> Dict[str, Any]:
    if path is None:
        path = get_role_triggers_path()
    if not path:
        return {"triggers": []}
    if not os.path.exists(path):
        # If the file does not exist yet, create it with an empty structure
        data: Dict[str, Any] = {"triggers": []}
        save_role_triggers(data, path)
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"triggers": []}
        data.setdefault("triggers", [])
        return data
    except Exception:
        return {"triggers": []}


def save_role_triggers(data: Dict[str, Any], path: str | None = None) -> None:
    if path is None:
        path = get_role_triggers_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
