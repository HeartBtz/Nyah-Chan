"""SQLite database manager for Nyah-Chan.

Single-file database replacing all JSON config stores.
Thread-safe, with WAL mode and an in-memory TTL cache.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyahchan.database")

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_db: Optional["Database"] = None

_GUILD_CONFIG_COLUMNS = frozenset({
    "prefix", "welcome_enabled", "welcome_channel_id", "welcome_message",
    "goodbye_enabled", "goodbye_channel_id", "goodbye_message",
    "mod_log_channel_id", "automod_enabled", "automod_bad_words",
    "automod_max_mentions", "automod_max_caps_percent",
    "ollama_enabled", "ollama_base_url", "ollama_model",
    "ollama_timeout", "ollama_system_prompt", "reactions_enabled",
})


def get_db() -> "Database":
    """Return the initialised database singleton."""
    assert _db is not None, "Database not initialised — call init_db() first"
    return _db


def init_db(path: str = "nyahchan.db") -> "Database":
    """Create (or open) the database and return the singleton."""
    global _db
    _db = Database(path)
    return _db


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------
class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_ttl = 30  # seconds
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        self._migrate_json()
        logger.info("Database ready: %s", path)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _create_tables(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    guild_id              TEXT PRIMARY KEY,
                    prefix                TEXT    DEFAULT '!',
                    welcome_enabled       INTEGER DEFAULT 0,
                    welcome_channel_id    TEXT,
                    welcome_message       TEXT    DEFAULT 'Bienvenue {mention} sur **{server}** ! 🎉',
                    goodbye_enabled       INTEGER DEFAULT 0,
                    goodbye_channel_id    TEXT,
                    goodbye_message       TEXT    DEFAULT '**{user}** a quitté **{server}**. Au revoir ! 👋',
                    mod_log_channel_id    TEXT,
                    automod_enabled       INTEGER DEFAULT 0,
                    automod_bad_words     TEXT    DEFAULT '',
                    automod_max_mentions  INTEGER DEFAULT 5,
                    automod_max_caps_percent INTEGER DEFAULT 80,
                    ollama_enabled        INTEGER DEFAULT 0,
                    ollama_base_url       TEXT    DEFAULT 'http://localhost:11434',
                    ollama_model          TEXT    DEFAULT 'llama3',
                    ollama_timeout        INTEGER DEFAULT 60,
                    ollama_system_prompt  TEXT    DEFAULT '',
                    reactions_enabled     INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS warn_escalation (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    TEXT    NOT NULL,
                    warn_count  INTEGER NOT NULL,
                    action      TEXT    NOT NULL,
                    action_param INTEGER DEFAULT 0,
                    UNIQUE(guild_id, warn_count)
                );

                CREATE TABLE IF NOT EXISTS keyword_responses (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id      TEXT NOT NULL,
                    triggers      TEXT NOT NULL,
                    title         TEXT NOT NULL,
                    description   TEXT DEFAULT '',
                    color         TEXT DEFAULT '',
                    fields        TEXT DEFAULT '[]',
                    footer        TEXT,
                    image_url     TEXT,
                    thumbnail_url TEXT
                );

                CREATE TABLE IF NOT EXISTS role_triggers (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id       TEXT NOT NULL,
                    trigger_word   TEXT NOT NULL,
                    role_name      TEXT NOT NULL,
                    remove_trigger TEXT
                );

                CREATE TABLE IF NOT EXISTS grant_commands (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id         TEXT NOT NULL,
                    name             TEXT NOT NULL,
                    role_name        TEXT NOT NULL,
                    allowed_user_ids TEXT NOT NULL,
                    gif_path         TEXT
                );

                CREATE TABLE IF NOT EXISTS warnings (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id     TEXT NOT NULL,
                    user_id      TEXT NOT NULL,
                    moderator_id TEXT NOT NULL,
                    reason       TEXT NOT NULL,
                    created_at   TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_warnings_guild      ON warnings(guild_id);
                CREATE INDEX IF NOT EXISTS idx_warnings_guild_user  ON warnings(guild_id, user_id);
                CREATE INDEX IF NOT EXISTS idx_kw_guild             ON keyword_responses(guild_id);
                CREATE INDEX IF NOT EXISTS idx_rt_guild             ON role_triggers(guild_id);
                CREATE INDEX IF NOT EXISTS idx_gc_guild             ON grant_commands(guild_id);
                CREATE INDEX IF NOT EXISTS idx_esc_guild            ON warn_escalation(guild_id);
            """)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _cache_get(self, key: str) -> Any:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self._cache_ttl:
            del self._cache[key]
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        self._cache[key] = (time.time(), value)

    def _cache_invalidate(self, prefix: str) -> None:
        keys = [k for k in self._cache if k.startswith(prefix)]
        for k in keys:
            del self._cache[k]

    # ------------------------------------------------------------------
    # Guild config
    # ------------------------------------------------------------------
    def get_guild_config(self, guild_id: str) -> Dict[str, Any]:
        cached = self._cache_get(f"cfg:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
            ).fetchone()
        if row is None:
            # Auto-create with defaults
            with self._lock:
                self._conn.execute(
                    "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
                    (guild_id,),
                )
                self._conn.commit()
                row = self._conn.execute(
                    "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
                ).fetchone()
        result = dict(row)
        self._cache_set(f"cfg:{guild_id}", result)
        return result

    def save_guild_config(self, guild_id: str, **kwargs: Any) -> None:
        # Only allow known columns
        safe = {k: v for k, v in kwargs.items() if k in _GUILD_CONFIG_COLUMNS}
        if not safe:
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
                (guild_id,),
            )
            sets = ", ".join(f"{k} = ?" for k in safe)
            vals = list(safe.values()) + [guild_id]
            self._conn.execute(
                f"UPDATE guild_config SET {sets} WHERE guild_id = ?", vals
            )
            self._conn.commit()
        self._cache_invalidate(f"cfg:{guild_id}")

    # ------------------------------------------------------------------
    # Keyword responses
    # ------------------------------------------------------------------
    def get_keywords(self, guild_id: str) -> List[Dict[str, Any]]:
        cached = self._cache_get(f"kw:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM keyword_responses WHERE guild_id = ? ORDER BY id",
                (guild_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["triggers"] = json.loads(d.get("triggers") or "[]")
            d["fields"] = json.loads(d.get("fields") or "[]")
            result.append(d)
        self._cache_set(f"kw:{guild_id}", result)
        return result

    def save_keywords(self, guild_id: str, keywords: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM keyword_responses WHERE guild_id = ?", (guild_id,)
            )
            for kw in keywords:
                self._conn.execute(
                    """INSERT INTO keyword_responses
                       (guild_id, triggers, title, description, color, fields,
                        footer, image_url, thumbnail_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        guild_id,
                        json.dumps(kw.get("triggers", []), ensure_ascii=False),
                        kw.get("title", ""),
                        kw.get("description", ""),
                        str(kw.get("color", "")),
                        json.dumps(kw.get("fields", []), ensure_ascii=False),
                        kw.get("footer"),
                        kw.get("image_url"),
                        kw.get("thumbnail_url"),
                    ),
                )
            self._conn.commit()
        self._cache_invalidate(f"kw:{guild_id}")

    # ------------------------------------------------------------------
    # Role triggers
    # ------------------------------------------------------------------
    def get_role_triggers(self, guild_id: str) -> List[Dict[str, Any]]:
        cached = self._cache_get(f"rt:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM role_triggers WHERE guild_id = ? ORDER BY id",
                (guild_id,),
            ).fetchall()
        result = [dict(r) for r in rows]
        self._cache_set(f"rt:{guild_id}", result)
        return result

    def save_role_triggers(self, guild_id: str, triggers: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM role_triggers WHERE guild_id = ?", (guild_id,)
            )
            for t in triggers:
                self._conn.execute(
                    """INSERT INTO role_triggers
                       (guild_id, trigger_word, role_name, remove_trigger)
                       VALUES (?, ?, ?, ?)""",
                    (
                        guild_id,
                        t.get("trigger_word", ""),
                        t.get("role_name", ""),
                        t.get("remove_trigger"),
                    ),
                )
            self._conn.commit()
        self._cache_invalidate(f"rt:{guild_id}")

    # ------------------------------------------------------------------
    # Grant commands
    # ------------------------------------------------------------------
    def get_grant_commands(self, guild_id: str) -> List[Dict[str, Any]]:
        cached = self._cache_get(f"gc:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM grant_commands WHERE guild_id = ? ORDER BY id",
                (guild_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["allowed_user_ids"] = json.loads(d.get("allowed_user_ids") or "[]")
            result.append(d)
        self._cache_set(f"gc:{guild_id}", result)
        return result

    def save_grant_commands(self, guild_id: str, commands: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM grant_commands WHERE guild_id = ?", (guild_id,)
            )
            for c in commands:
                self._conn.execute(
                    """INSERT INTO grant_commands
                       (guild_id, name, role_name, allowed_user_ids, gif_path)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        guild_id,
                        c.get("name", ""),
                        c.get("role_name", ""),
                        json.dumps(c.get("allowed_user_ids", []), ensure_ascii=False),
                        c.get("gif_path"),
                    ),
                )
            self._conn.commit()
        self._cache_invalidate(f"gc:{guild_id}")

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------
    def add_warning(
        self, guild_id: str, user_id: str, moderator_id: str, reason: str
    ) -> Dict[str, Any]:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (guild_id, user_id, moderator_id, reason, now),
            )
            self._conn.commit()
            wid = cur.lastrowid
        return {
            "id": wid,
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "created_at": now,
        }

    def get_warnings(
        self, guild_id: str, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            if user_id:
                rows = self._conn.execute(
                    "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
                    (guild_id, user_id),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM warnings WHERE guild_id = ? ORDER BY id DESC",
                    (guild_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_warning_count(self, guild_id: str, user_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM warnings WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
        return row["cnt"] if row else 0

    def remove_warning(self, guild_id: str, warning_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM warnings WHERE guild_id = ? AND id = ?",
                (guild_id, warning_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def get_all_warnings(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM warnings ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def total_warning_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) as cnt FROM warnings").fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Warn escalation rules
    # ------------------------------------------------------------------
    def get_escalation_rules(self, guild_id: str) -> List[Dict[str, Any]]:
        cached = self._cache_get(f"esc:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM warn_escalation WHERE guild_id = ? ORDER BY warn_count",
                (guild_id,),
            ).fetchall()
        result = [dict(r) for r in rows]
        self._cache_set(f"esc:{guild_id}", result)
        return result

    def save_escalation_rules(
        self, guild_id: str, rules: List[Dict[str, Any]]
    ) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM warn_escalation WHERE guild_id = ?", (guild_id,)
            )
            for r in rules:
                self._conn.execute(
                    """INSERT INTO warn_escalation
                       (guild_id, warn_count, action, action_param)
                       VALUES (?, ?, ?, ?)""",
                    (
                        guild_id,
                        int(r.get("warn_count", 0)),
                        r.get("action", "timeout"),
                        int(r.get("action_param", 0)),
                    ),
                )
            self._conn.commit()
        self._cache_invalidate(f"esc:{guild_id}")

    # ------------------------------------------------------------------
    # Migration from legacy JSON files
    # ------------------------------------------------------------------
    def _migrate_json(self) -> None:
        """One-time import from old JSON files if they exist."""
        self._migrate_warnings_json()

    def _migrate_warnings_json(self) -> None:
        p = Path("moderation_warnings.json")
        if not p.exists():
            return
        # Only migrate if warnings table is empty
        with self._lock:
            cnt = self._conn.execute("SELECT COUNT(*) as c FROM warnings").fetchone()
        if cnt and cnt["c"] > 0:
            return
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            data = raw.get("warnings", {})
            count = 0
            for guild_id, users in data.items():
                for user_id, warns in users.items():
                    for w in warns:
                        with self._lock:
                            self._conn.execute(
                                """INSERT INTO warnings
                                   (guild_id, user_id, moderator_id, reason, created_at)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (
                                    guild_id,
                                    user_id,
                                    str(w.get("moderator_id", "")),
                                    w.get("reason", ""),
                                    w.get("created_at", ""),
                                ),
                            )
                            count += 1
            with self._lock:
                self._conn.commit()
            logger.info("Migrated %d warnings from moderation_warnings.json", count)
            p.rename(p.with_suffix(".json.migrated"))
        except Exception as e:
            logger.error("Failed to migrate warnings JSON: %s", e)
