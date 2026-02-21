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
from datetime import datetime, timezone
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
    # Anti-raid
    "antiraid_enabled", "antiraid_join_count", "antiraid_join_seconds",
    "antiraid_action",
    # Anti-spam
    "antispam_enabled", "antispam_max_messages", "antispam_interval_seconds",
    "antispam_mute_minutes",
    # Anti-link
    "antilink_enabled", "antilink_whitelist_domains",
    "antilink_block_discord_invites",
    # Audit log
    "audit_log_enabled", "audit_log_channel_id",
    # Starboard
    "starboard_enabled", "starboard_channel_id", "starboard_threshold",
    "starboard_emoji",
    # XP / levels
    "xp_enabled", "xp_min", "xp_max", "xp_cooldown_seconds",
    "xp_level_up_channel_id", "xp_level_up_message",
    # Tickets
    "tickets_enabled", "tickets_category_id", "tickets_log_channel_id",
    "tickets_support_role",
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
        self._lock = threading.RLock()
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
                    reactions_enabled     INTEGER DEFAULT 1,
                    -- Anti-raid
                    antiraid_enabled          INTEGER DEFAULT 0,
                    antiraid_join_count       INTEGER DEFAULT 10,
                    antiraid_join_seconds     INTEGER DEFAULT 30,
                    antiraid_action           TEXT    DEFAULT 'kick',
                    -- Anti-spam
                    antispam_enabled          INTEGER DEFAULT 0,
                    antispam_max_messages     INTEGER DEFAULT 5,
                    antispam_interval_seconds INTEGER DEFAULT 5,
                    antispam_mute_minutes     INTEGER DEFAULT 5,
                    -- Anti-link
                    antilink_enabled              INTEGER DEFAULT 0,
                    antilink_whitelist_domains    TEXT    DEFAULT '',
                    antilink_block_discord_invites INTEGER DEFAULT 1,
                    -- Audit log (message edit/delete, voice, nickname)
                    audit_log_enabled     INTEGER DEFAULT 0,
                    audit_log_channel_id  TEXT,
                    -- Starboard
                    starboard_enabled     INTEGER DEFAULT 0,
                    starboard_channel_id  TEXT,
                    starboard_threshold   INTEGER DEFAULT 3,
                    starboard_emoji       TEXT    DEFAULT '⭐',
                    -- XP / levels
                    xp_enabled            INTEGER DEFAULT 0,
                    xp_min                INTEGER DEFAULT 15,
                    xp_max                INTEGER DEFAULT 25,
                    xp_cooldown_seconds   INTEGER DEFAULT 60,
                    xp_level_up_channel_id TEXT,
                    xp_level_up_message   TEXT    DEFAULT '🎉 {mention} est passé au niveau **{level}** !',
                    -- Tickets
                    tickets_enabled       INTEGER DEFAULT 0,
                    tickets_category_id   TEXT,
                    tickets_log_channel_id TEXT,
                    tickets_support_role  TEXT
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

                -- XP / Levels
                CREATE TABLE IF NOT EXISTS user_xp (
                    guild_id   TEXT NOT NULL,
                    user_id    TEXT NOT NULL,
                    xp         INTEGER DEFAULT 0,
                    level      INTEGER DEFAULT 0,
                    last_xp_at TEXT,
                    PRIMARY KEY (guild_id, user_id)
                );

                -- XP level-up role rewards
                CREATE TABLE IF NOT EXISTS xp_role_rewards (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT    NOT NULL,
                    level    INTEGER NOT NULL,
                    role_name TEXT   NOT NULL,
                    UNIQUE(guild_id, level)
                );

                -- Tempbans
                CREATE TABLE IF NOT EXISTS tempbans (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id  TEXT NOT NULL,
                    user_id   TEXT NOT NULL,
                    mod_id    TEXT NOT NULL,
                    reason    TEXT,
                    expires_at TEXT NOT NULL,
                    unbanned  INTEGER DEFAULT 0
                );

                -- Reminders
                CREATE TABLE IF NOT EXISTS reminders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id   TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    user_id    TEXT NOT NULL,
                    message    TEXT NOT NULL,
                    remind_at  TEXT NOT NULL,
                    done       INTEGER DEFAULT 0
                );

                -- Custom commands
                CREATE TABLE IF NOT EXISTS custom_commands (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    response    TEXT NOT NULL,
                    embed       INTEGER DEFAULT 0,
                    color       TEXT  DEFAULT '',
                    UNIQUE(guild_id, name)
                );

                -- Scheduled messages
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    TEXT NOT NULL,
                    channel_id  TEXT NOT NULL,
                    message     TEXT NOT NULL,
                    cron        TEXT DEFAULT '',
                    next_run    TEXT NOT NULL,
                    recurring   INTEGER DEFAULT 0,
                    done        INTEGER DEFAULT 0
                );

                -- Reaction roles
                CREATE TABLE IF NOT EXISTS reaction_roles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    TEXT NOT NULL,
                    channel_id  TEXT NOT NULL,
                    message_id  TEXT NOT NULL,
                    emoji       TEXT NOT NULL,
                    role_name   TEXT NOT NULL,
                    UNIQUE(guild_id, message_id, emoji)
                );

                -- Starboard tracking (which messages have been posted)
                CREATE TABLE IF NOT EXISTS starboard_entries (
                    guild_id           TEXT NOT NULL,
                    source_message_id  TEXT NOT NULL,
                    board_message_id   TEXT NOT NULL,
                    PRIMARY KEY (guild_id, source_message_id)
                );

                -- Giveaways
                CREATE TABLE IF NOT EXISTS giveaways (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    TEXT NOT NULL,
                    channel_id  TEXT NOT NULL,
                    message_id  TEXT,
                    prize       TEXT NOT NULL,
                    winners     INTEGER DEFAULT 1,
                    ends_at     TEXT NOT NULL,
                    ended       INTEGER DEFAULT 0,
                    host_id     TEXT NOT NULL
                );

                -- WebUI audit log
                CREATE TABLE IF NOT EXISTS webui_audit_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id   TEXT NOT NULL,
                    user_id    TEXT NOT NULL,
                    username   TEXT NOT NULL,
                    action     TEXT NOT NULL,
                    detail     TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                -- Activity stats (message counts per day)
                CREATE TABLE IF NOT EXISTS activity_stats (
                    guild_id TEXT NOT NULL,
                    date     TEXT NOT NULL,
                    messages INTEGER DEFAULT 0,
                    joins    INTEGER DEFAULT 0,
                    leaves   INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, date)
                );

                -- Polls
                CREATE TABLE IF NOT EXISTS polls (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id   TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_id TEXT,
                    question   TEXT NOT NULL,
                    options    TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    ends_at    TEXT,
                    ended      INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_warnings_guild      ON warnings(guild_id);
                CREATE INDEX IF NOT EXISTS idx_warnings_guild_user  ON warnings(guild_id, user_id);
                CREATE INDEX IF NOT EXISTS idx_kw_guild             ON keyword_responses(guild_id);
                CREATE INDEX IF NOT EXISTS idx_rt_guild             ON role_triggers(guild_id);
                CREATE INDEX IF NOT EXISTS idx_gc_guild             ON grant_commands(guild_id);
                CREATE INDEX IF NOT EXISTS idx_esc_guild            ON warn_escalation(guild_id);
                CREATE INDEX IF NOT EXISTS idx_xp_guild             ON user_xp(guild_id);
                CREATE INDEX IF NOT EXISTS idx_tempban_expires       ON tempbans(expires_at);
                CREATE INDEX IF NOT EXISTS idx_reminder_at           ON reminders(remind_at);
                CREATE INDEX IF NOT EXISTS idx_scheduled_next        ON scheduled_messages(next_run);
                CREATE INDEX IF NOT EXISTS idx_giveaway_ends         ON giveaways(ends_at);
                CREATE INDEX IF NOT EXISTS idx_activity_guild_date   ON activity_stats(guild_id, date);
                CREATE INDEX IF NOT EXISTS idx_audit_guild           ON webui_audit_log(guild_id);
            """)
            self._conn.commit()
            # Auto-add new columns to existing databases
            self._ensure_columns()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _ensure_columns(self) -> None:
        """Add missing columns to guild_config for upgrades."""
        with self._lock:
            existing = {row[1] for row in self._conn.execute("PRAGMA table_info(guild_config)").fetchall()}
        new_cols = {
            "antiraid_enabled": "INTEGER DEFAULT 0",
            "antiraid_join_count": "INTEGER DEFAULT 10",
            "antiraid_join_seconds": "INTEGER DEFAULT 30",
            "antiraid_action": "TEXT DEFAULT 'kick'",
            "antispam_enabled": "INTEGER DEFAULT 0",
            "antispam_max_messages": "INTEGER DEFAULT 5",
            "antispam_interval_seconds": "INTEGER DEFAULT 5",
            "antispam_mute_minutes": "INTEGER DEFAULT 5",
            "antilink_enabled": "INTEGER DEFAULT 0",
            "antilink_whitelist_domains": "TEXT DEFAULT ''",
            "antilink_block_discord_invites": "INTEGER DEFAULT 1",
            "audit_log_enabled": "INTEGER DEFAULT 0",
            "audit_log_channel_id": "TEXT",
            "starboard_enabled": "INTEGER DEFAULT 0",
            "starboard_channel_id": "TEXT",
            "starboard_threshold": "INTEGER DEFAULT 3",
            "starboard_emoji": "TEXT DEFAULT '⭐'",
            "xp_enabled": "INTEGER DEFAULT 0",
            "xp_min": "INTEGER DEFAULT 15",
            "xp_max": "INTEGER DEFAULT 25",
            "xp_cooldown_seconds": "INTEGER DEFAULT 60",
            "xp_level_up_channel_id": "TEXT",
            "xp_level_up_message": "TEXT DEFAULT '🎉 {mention} est passé au niveau **{level}** !'",
            "tickets_enabled": "INTEGER DEFAULT 0",
            "tickets_category_id": "TEXT",
            "tickets_log_channel_id": "TEXT",
            "tickets_support_role": "TEXT",
        }
        with self._lock:
            for col, typedef in new_cols.items():
                if col not in existing:
                    try:
                        self._conn.execute(f"ALTER TABLE guild_config ADD COLUMN {col} {typedef}")
                    except Exception:
                        pass
            self._conn.commit()

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
    # XP / Levels
    # ------------------------------------------------------------------
    def get_user_xp(self, guild_id: str, user_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM user_xp WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
        if row:
            return dict(row)
        return {"guild_id": guild_id, "user_id": user_id, "xp": 0, "level": 0, "last_xp_at": None}

    def add_xp(self, guild_id: str, user_id: str, amount: int) -> Dict[str, Any]:
        """Add XP, recalculate level, return updated record + old level."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                """INSERT INTO user_xp (guild_id, user_id, xp, level, last_xp_at)
                   VALUES (?, ?, ?, 0, ?)
                   ON CONFLICT(guild_id, user_id)
                   DO UPDATE SET xp = xp + ?, last_xp_at = ?""",
                (guild_id, user_id, amount, now, amount, now),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM user_xp WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
        d = dict(row)
        new_level = self._calc_level(d["xp"])
        if new_level != d["level"]:
            with self._lock:
                self._conn.execute(
                    "UPDATE user_xp SET level = ? WHERE guild_id = ? AND user_id = ?",
                    (new_level, guild_id, user_id),
                )
                self._conn.commit()
            d["old_level"] = d["level"]
            d["level"] = new_level
        else:
            d["old_level"] = d["level"]
        return d

    @staticmethod
    def _calc_level(xp: int) -> int:
        """XP formula: level N requires 5*(N^2)+50*N+100 total XP."""
        level = 0
        total_needed = 0
        while True:
            needed = 5 * (level ** 2) + 50 * level + 100
            total_needed += needed
            if xp < total_needed:
                break
            level += 1
        return level

    def get_xp_leaderboard(self, guild_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM user_xp WHERE guild_id = ? ORDER BY xp DESC LIMIT ?",
                (guild_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_xp_role_rewards(self, guild_id: str) -> List[Dict[str, Any]]:
        cached = self._cache_get(f"xprr:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM xp_role_rewards WHERE guild_id = ? ORDER BY level",
                (guild_id,),
            ).fetchall()
        result = [dict(r) for r in rows]
        self._cache_set(f"xprr:{guild_id}", result)
        return result

    def save_xp_role_rewards(self, guild_id: str, rewards: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM xp_role_rewards WHERE guild_id = ?", (guild_id,))
            for r in rewards:
                self._conn.execute(
                    "INSERT OR REPLACE INTO xp_role_rewards (guild_id, level, role_name) VALUES (?, ?, ?)",
                    (guild_id, int(r.get("level", 0)), r.get("role_name", "")),
                )
            self._conn.commit()
        self._cache_invalidate(f"xprr:{guild_id}")

    # ------------------------------------------------------------------
    # Tempbans
    # ------------------------------------------------------------------
    def add_tempban(self, guild_id: str, user_id: str, mod_id: str,
                    reason: str, expires_at: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO tempbans (guild_id, user_id, mod_id, reason, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (guild_id, user_id, mod_id, reason, expires_at),
            )
            self._conn.commit()
        return cur.lastrowid

    def get_expired_tempbans(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tempbans WHERE unbanned = 0 AND expires_at <= ?",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_tempban_done(self, tempban_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE tempbans SET unbanned = 1 WHERE id = ?", (tempban_id,)
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------
    def add_reminder(self, guild_id: str, channel_id: str, user_id: str,
                     message: str, remind_at: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO reminders (guild_id, channel_id, user_id, message, remind_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (guild_id, channel_id, user_id, message, remind_at),
            )
            self._conn.commit()
        return cur.lastrowid

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reminders WHERE done = 0 AND remind_at <= ?",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_reminder_done(self, reminder_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Custom commands
    # ------------------------------------------------------------------
    def get_custom_commands(self, guild_id: str) -> List[Dict[str, Any]]:
        cached = self._cache_get(f"cc:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM custom_commands WHERE guild_id = ? ORDER BY name",
                (guild_id,),
            ).fetchall()
        result = [dict(r) for r in rows]
        self._cache_set(f"cc:{guild_id}", result)
        return result

    def save_custom_commands(self, guild_id: str, commands: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM custom_commands WHERE guild_id = ?", (guild_id,))
            for c in commands:
                self._conn.execute(
                    """INSERT INTO custom_commands (guild_id, name, response, embed, color)
                       VALUES (?, ?, ?, ?, ?)""",
                    (guild_id, c.get("name", ""), c.get("response", ""),
                     int(c.get("embed", 0)), c.get("color", "")),
                )
            self._conn.commit()
        self._cache_invalidate(f"cc:{guild_id}")

    # ------------------------------------------------------------------
    # Scheduled messages
    # ------------------------------------------------------------------
    def get_scheduled_messages(self, guild_id: str) -> List[Dict[str, Any]]:
        cached = self._cache_get(f"sm:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM scheduled_messages WHERE guild_id = ? ORDER BY next_run",
                (guild_id,),
            ).fetchall()
        result = [dict(r) for r in rows]
        self._cache_set(f"sm:{guild_id}", result)
        return result

    def save_scheduled_messages(self, guild_id: str, messages: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM scheduled_messages WHERE guild_id = ?", (guild_id,))
            for m in messages:
                self._conn.execute(
                    """INSERT INTO scheduled_messages
                       (guild_id, channel_id, message, cron, next_run, recurring, done)
                       VALUES (?, ?, ?, ?, ?, ?, 0)""",
                    (guild_id, m.get("channel_id", ""), m.get("message", ""),
                     m.get("cron", ""), m.get("next_run", ""), int(m.get("recurring", 0))),
                )
            self._conn.commit()
        self._cache_invalidate(f"sm:{guild_id}")

    def get_due_scheduled(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM scheduled_messages WHERE done = 0 AND next_run <= ?",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_scheduled_done(self, sid: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE scheduled_messages SET done = 1 WHERE id = ?", (sid,)
            )
            self._conn.commit()
        # Invalidate caches for all guilds (simple approach)
        keys = [k for k in self._cache if k.startswith("sm:")]
        for k in keys:
            del self._cache[k]

    # ------------------------------------------------------------------
    # Reaction roles
    # ------------------------------------------------------------------
    def get_reaction_roles(self, guild_id: str) -> List[Dict[str, Any]]:
        cached = self._cache_get(f"rr:{guild_id}")
        if cached is not None:
            return cached
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reaction_roles WHERE guild_id = ? ORDER BY id",
                (guild_id,),
            ).fetchall()
        result = [dict(r) for r in rows]
        self._cache_set(f"rr:{guild_id}", result)
        return result

    def save_reaction_roles(self, guild_id: str, rrs: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM reaction_roles WHERE guild_id = ?", (guild_id,))
            for rr in rrs:
                self._conn.execute(
                    """INSERT OR REPLACE INTO reaction_roles
                       (guild_id, channel_id, message_id, emoji, role_name)
                       VALUES (?, ?, ?, ?, ?)""",
                    (guild_id, rr.get("channel_id", ""), rr.get("message_id", ""),
                     rr.get("emoji", ""), rr.get("role_name", "")),
                )
            self._conn.commit()
        self._cache_invalidate(f"rr:{guild_id}")

    def find_reaction_role(self, guild_id: str, message_id: str, emoji: str) -> Optional[Dict[str, Any]]:
        rrs = self.get_reaction_roles(guild_id)
        for rr in rrs:
            if rr["message_id"] == message_id and rr["emoji"] == emoji:
                return rr
        return None

    # ------------------------------------------------------------------
    # Starboard
    # ------------------------------------------------------------------
    def get_starboard_entry(self, guild_id: str, source_msg_id: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT board_message_id FROM starboard_entries WHERE guild_id = ? AND source_message_id = ?",
                (guild_id, source_msg_id),
            ).fetchone()
        return row["board_message_id"] if row else None

    def save_starboard_entry(self, guild_id: str, source_msg_id: str, board_msg_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO starboard_entries (guild_id, source_message_id, board_message_id) VALUES (?, ?, ?)",
                (guild_id, source_msg_id, board_msg_id),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Giveaways
    # ------------------------------------------------------------------
    def create_giveaway(self, guild_id: str, channel_id: str, prize: str,
                        winners: int, ends_at: str, host_id: str, message_id: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, ends_at, host_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (guild_id, channel_id, message_id, prize, winners, ends_at, host_id),
            )
            self._conn.commit()
        return cur.lastrowid

    def set_giveaway_message(self, giveaway_id: int, message_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE giveaways SET message_id = ? WHERE id = ?",
                (message_id, giveaway_id),
            )
            self._conn.commit()

    def get_ended_giveaways(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM giveaways WHERE ended = 0 AND ends_at <= ?",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_giveaway_ended(self, giveaway_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,)
            )
            self._conn.commit()

    def get_active_giveaways(self, guild_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM giveaways WHERE guild_id = ? AND ended = 0 ORDER BY ends_at",
                (guild_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # WebUI audit log
    # ------------------------------------------------------------------
    def add_audit_log(self, guild_id: str, user_id: str, username: str,
                      action: str, detail: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                """INSERT INTO webui_audit_log (guild_id, user_id, username, action, detail, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (guild_id, user_id, username, action, detail, now),
            )
            self._conn.commit()

    def get_audit_logs(self, guild_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM webui_audit_log WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Activity stats
    # ------------------------------------------------------------------
    def increment_activity(self, guild_id: str, field: str = "messages") -> None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if field not in ("messages", "joins", "leaves"):
            return
        with self._lock:
            self._conn.execute(
                f"""INSERT INTO activity_stats (guild_id, date, {field})
                    VALUES (?, ?, 1)
                    ON CONFLICT(guild_id, date)
                    DO UPDATE SET {field} = {field} + 1""",
                (guild_id, date),
            )
            self._conn.commit()

    def get_activity_stats(self, guild_id: str, days: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM activity_stats WHERE guild_id = ? ORDER BY date DESC LIMIT ?",
                (guild_id, days),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ------------------------------------------------------------------
    # Polls
    # ------------------------------------------------------------------
    def create_poll(self, guild_id: str, channel_id: str, question: str,
                    options: List[str], created_by: str, ends_at: str = "",
                    message_id: str = "") -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO polls (guild_id, channel_id, message_id, question, options, created_by, ends_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (guild_id, channel_id, message_id, question,
                 json.dumps(options, ensure_ascii=False), created_by, ends_at),
            )
            self._conn.commit()
        return cur.lastrowid

    def set_poll_message(self, poll_id: int, message_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE polls SET message_id = ? WHERE id = ?", (message_id, poll_id)
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Config backup
    # ------------------------------------------------------------------
    def export_guild_config(self, guild_id: str) -> Dict[str, Any]:
        """Export all config for a guild as a dict for backup."""
        return {
            "guild_config": self.get_guild_config(guild_id),
            "keywords": self.get_keywords(guild_id),
            "role_triggers": self.get_role_triggers(guild_id),
            "grant_commands": self.get_grant_commands(guild_id),
            "escalation": self.get_escalation_rules(guild_id),
            "custom_commands": self.get_custom_commands(guild_id),
            "reaction_roles": self.get_reaction_roles(guild_id),
            "xp_role_rewards": self.get_xp_role_rewards(guild_id),
            "scheduled_messages": self.get_scheduled_messages(guild_id),
        }

    def import_guild_config(self, guild_id: str, data: Dict[str, Any]) -> None:
        """Import config backup for a guild."""
        cfg = data.get("guild_config", {})
        cfg.pop("guild_id", None)
        if cfg:
            self.save_guild_config(guild_id, **cfg)
        if "keywords" in data:
            self.save_keywords(guild_id, data["keywords"])
        if "role_triggers" in data:
            self.save_role_triggers(guild_id, data["role_triggers"])
        if "grant_commands" in data:
            self.save_grant_commands(guild_id, data["grant_commands"])
        if "escalation" in data:
            self.save_escalation_rules(guild_id, data["escalation"])
        if "custom_commands" in data:
            self.save_custom_commands(guild_id, data["custom_commands"])
        if "reaction_roles" in data:
            self.save_reaction_roles(guild_id, data["reaction_roles"])
        if "xp_role_rewards" in data:
            self.save_xp_role_rewards(guild_id, data["xp_role_rewards"])
        if "scheduled_messages" in data:
            self.save_scheduled_messages(guild_id, data["scheduled_messages"])

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
