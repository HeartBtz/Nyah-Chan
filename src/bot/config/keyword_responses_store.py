from __future__ import annotations

import json
import os
from typing import Any, Dict


DEFAULT_KEYWORD_RESPONSES_PATH = "keyword_responses.json"
KEYWORD_RESPONSES_ENV = "KEYWORD_RESPONSES_CONFIG"


def get_keyword_responses_path() -> str:
    """Return configured keyword responses path or default.

    The .env variable KEYWORD_RESPONSES_CONFIG can override the default path.
    """
    return os.getenv(KEYWORD_RESPONSES_ENV, DEFAULT_KEYWORD_RESPONSES_PATH)


def load_keyword_responses(path: str | None = None) -> Dict[str, Any]:
    """Load keyword responses JSON.

    Returns an empty structure if file does not exist or is invalid.
    """
    if path is None:
        path = get_keyword_responses_path()
    if not path:
        return {"embeds": []}
    if not os.path.exists(path):
        # If the file does not exist yet, create it with an empty structure
        data: Dict[str, Any] = {"embeds": []}
        save_keyword_responses(data, path)
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"embeds": []}
        data.setdefault("embeds", [])
        return data
    except Exception:
        return {"embeds": []}


def save_keyword_responses(data: Dict[str, Any], path: str | None = None) -> None:
    """Save keyword responses JSON to disk.

    Overwrites the target file.
    """
    if path is None:
        path = get_keyword_responses_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
