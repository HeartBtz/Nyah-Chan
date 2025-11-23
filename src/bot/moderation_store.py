from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger("nyahchan.moderation.store")


DEFAULT_WARNINGS_PATH = "moderation_warnings.json"


@dataclass
class WarningEntry:
    id: int
    user_id: int
    moderator_id: int
    guild_id: int
    reason: str
    created_at: str  # ISO 8601


class WarningStore:
    """Stockage simple des avertissements (warns) dans un JSON.

    Structure du fichier :
    {
      "guild_id": {
        "user_id": [WarningEntry, ...]
      },
      ...
    }
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("MOD_WARNINGS_PATH", DEFAULT_WARNINGS_PATH))
        self._data: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self._last_id: int = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            logger.info(f"Fichier de warns absent, création: {self.path}")
            self._data = {}
            self._last_id = 0
            self._save()
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"Erreur de lecture du fichier de warns {self.path}: {e}")
            self._data = {}
            self._last_id = 0
            return

        self._data = raw.get("warnings", {}) if isinstance(raw, dict) else {}
        self._last_id = int(raw.get("last_id", 0)) if isinstance(raw, dict) else 0

    def _save(self) -> None:
        payload = {
            "last_id": self._last_id,
            "warnings": self._data,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erreur d'écriture du fichier de warns {self.path}: {e}")

    def _next_id(self) -> int:
        self._last_id += 1
        return self._last_id

    def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> WarningEntry:
        wid = self._next_id()
        entry = WarningEntry(
            id=wid,
            user_id=user_id,
            moderator_id=moderator_id,
            guild_id=guild_id,
            reason=reason,
            created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        )
        gkey = str(guild_id)
        ukey = str(user_id)
        guild_block = self._data.setdefault(gkey, {})
        user_list = guild_block.setdefault(ukey, [])
        user_list.append(asdict(entry))
        self._save()
        return entry

    def get_warnings(self, guild_id: int, user_id: int) -> List[WarningEntry]:
        gkey = str(guild_id)
        ukey = str(user_id)
        raw_list = self._data.get(gkey, {}).get(ukey, [])
        out: List[WarningEntry] = []
        for obj in raw_list:
            try:
                out.append(WarningEntry(**obj))
            except Exception:
                continue
        return out

    def remove_warning(self, guild_id: int, user_id: int, warning_id: int) -> bool:
        gkey = str(guild_id)
        ukey = str(user_id)
        guild_block = self._data.get(gkey)
        if not guild_block:
            return False
        user_list = guild_block.get(ukey)
        if not user_list:
            return False
        new_list = [w for w in user_list if int(w.get("id", 0)) != int(warning_id)]
        if len(new_list) == len(user_list):
            return False
        guild_block[ukey] = new_list
        self._save()
        return True
