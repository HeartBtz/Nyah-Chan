from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

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
    """Thread-safe JSON-backed warning storage.

    Structure:
    {
      "last_id": int,
      "warnings": {
        "guild_id": {
          "user_id": [WarningEntry, ...]
        }
      }
    }
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("MOD_WARNINGS_PATH", DEFAULT_WARNINGS_PATH))
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self._last_id: int = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            logger.info("Warnings file not found, creating: %s", self.path)
            self._data = {}
            self._last_id = 0
            self._save()
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error("Error reading warnings file %s: %s", self.path, e)
            self._data = {}
            self._last_id = 0
            return

        if isinstance(raw, dict):
            self._data = raw.get("warnings", {})
            self._last_id = int(raw.get("last_id", 0))
        else:
            self._data = {}
            self._last_id = 0

    def _save(self) -> None:
        payload = {
            "last_id": self._last_id,
            "warnings": self._data,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Write to temp file first, then rename for atomicity
            tmp_path = self.path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp_path.replace(self.path)
        except Exception as e:
            logger.error("Error writing warnings file %s: %s", self.path, e)

    def _next_id(self) -> int:
        self._last_id += 1
        return self._last_id

    def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str) -> WarningEntry:
        with self._lock:
            wid = self._next_id()
            entry = WarningEntry(
                id=wid,
                user_id=user_id,
                moderator_id=moderator_id,
                guild_id=guild_id,
                reason=reason,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            gkey = str(guild_id)
            ukey = str(user_id)
            self._data.setdefault(gkey, {}).setdefault(ukey, []).append(asdict(entry))
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

    def get_all_warnings_for_guild(self, guild_id: int) -> List[WarningEntry]:
        """Return all warnings for a guild (for dashboard)."""
        gkey = str(guild_id)
        guild_data = self._data.get(gkey, {})
        out: List[WarningEntry] = []
        for user_list in guild_data.values():
            for obj in user_list:
                try:
                    out.append(WarningEntry(**obj))
                except Exception:
                    continue
        out.sort(key=lambda w: w.id, reverse=True)
        return out

    def remove_warning(self, guild_id: int, user_id: int, warning_id: int) -> bool:
        with self._lock:
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

    def get_total_count(self) -> int:
        """Return total number of warnings across all guilds."""
        total = 0
        for guild_data in self._data.values():
            for user_list in guild_data.values():
                total += len(user_list)
        return total
