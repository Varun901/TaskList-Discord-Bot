from __future__ import annotations
import sqlite3
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any

import pytz
from config import DATABASE_PATH, TIMEZONE

log = logging.getLogger("Database")


class Database:
    def __init__(self):
        self.path = DATABASE_PATH
        self._init_db()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id      INTEGER PRIMARY KEY,
                    guild_id     INTEGER NOT NULL,
                    source       TEXT    NOT NULL,
                    calendar_id  TEXT    NOT NULL,
                    channel_id   INTEGER NOT NULL,
                    notion_token TEXT,
                    created_at   TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS completed_tasks (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    task_name    TEXT    NOT NULL,
                    source       TEXT    DEFAULT 'calendar',
                    completed_at TEXT    DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS manual_tasks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    name        TEXT    NOT NULL,
                    description TEXT    DEFAULT '',
                    due_date    TEXT,
                    done        INTEGER DEFAULT 0,
                    created_at  TEXT    DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    task_name   TEXT    NOT NULL,
                    remind_at   TEXT    NOT NULL,
                    fired       INTEGER DEFAULT 0,
                    snoozed     INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)
        log.info("Database initialised.")

    # ── Users ─────────────────────────────────────────────────────────────────

    def upsert_user(self, user_id, guild_id, source, calendar_id, channel_id, notion_token=None):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO users (user_id, guild_id, source, calendar_id, channel_id, notion_token)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       guild_id=excluded.guild_id, source=excluded.source,
                       calendar_id=excluded.calendar_id, channel_id=excluded.channel_id,
                       notion_token=excluded.notion_token""",
                (user_id, guild_id, source, calendar_id, channel_id, notion_token),
            )

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_all_users(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]

    def delete_user(self, user_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    # ── Manual Tasks ──────────────────────────────────────────────────────────

    def add_manual_task(self, user_id: int, name: str, description: str = "", due_date: Optional[date] = None) -> Optional[int]:
        due_str = due_date.isoformat() if due_date else None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO manual_tasks (user_id, name, description, due_date) VALUES (?, ?, ?, ?)",
                (user_id, name, description, due_str),
            )
            return cur.lastrowid

    def get_manual_tasks(self, user_id: int, target_date: Optional[date] = None, include_done: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM manual_tasks WHERE user_id = ?"
        params: list = [user_id]
        if not include_done:
            query += " AND done = 0"
        if target_date is not None:
            query += " AND (due_date = ? OR due_date IS NULL)"
            params.append(target_date.isoformat())
        query += " ORDER BY due_date ASC, created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d["due_date"]:
                    d["due_date"] = date.fromisoformat(d["due_date"])
                result.append(d)
            return result

    def complete_manual_task(self, user_id: int, name_fragment: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name FROM manual_tasks WHERE user_id = ? AND done = 0 AND name LIKE ?",
                (user_id, f"%{name_fragment}%"),
            ).fetchone()
            if not row:
                return None
            conn.execute("UPDATE manual_tasks SET done = 1 WHERE id = ?", (row["id"],))
            conn.execute(
                "INSERT INTO completed_tasks (user_id, task_name, source) VALUES (?, ?, 'manual')",
                (user_id, row["name"]),
            )
            return row["name"]

    def delete_manual_task(self, user_id: int, name_fragment: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name FROM manual_tasks WHERE user_id = ? AND name LIKE ?",
                (user_id, f"%{name_fragment}%"),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM manual_tasks WHERE id = ?", (row["id"],))
            return row["name"]

    # ── Completed Tasks ───────────────────────────────────────────────────────

    def complete_calendar_task(self, user_id: int, task_name: str) -> Optional[str]:
        today = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT task_name FROM completed_tasks WHERE user_id=? AND task_name LIKE ? AND completed_at LIKE ? AND source='calendar'",
                (user_id, f"%{task_name}%", f"{today}%"),
            ).fetchone()
            if existing:
                return existing["task_name"]
            conn.execute(
                "INSERT INTO completed_tasks (user_id, task_name, source) VALUES (?, ?, 'calendar')",
                (user_id, task_name.strip()),
            )
            return task_name.strip()

    def get_completed_today(self, user_id: int) -> List[str]:
        today = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_name FROM completed_tasks WHERE user_id=? AND completed_at LIKE ?",
                (user_id, f"{today}%"),
            ).fetchall()
            return [r["task_name"] for r in rows]

    # ── Reminders ─────────────────────────────────────────────────────────────

    def set_reminder(self, user_id: int, task_name: str, remind_at: datetime) -> str:
        # Store as plain UTC string (no offset suffix) so SQLite string comparison works correctly.
        remind_utc = remind_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reminders (user_id, task_name, remind_at) VALUES (?, ?, ?)",
                (user_id, task_name.strip(), remind_utc),
            )
        return task_name.strip()

    def get_reminders(self, user_id: int) -> List[Dict[str, Any]]:
        tz = pytz.timezone(TIMEZONE)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE user_id=? AND fired=0 ORDER BY remind_at",
                (user_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            # Stored as plain UTC string; attach UTC tzinfo before converting to local.
            d["remind_at"] = (
                datetime.fromisoformat(d["remind_at"])
                .replace(tzinfo=timezone.utc)
                .astimezone(tz)
            )
            result.append(d)
        return result

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        # Use the same plain UTC format used when storing reminders.
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM reminders WHERE fired=0 AND remind_at<=?", (now_utc,)
            ).fetchall()]

    def mark_reminder_fired(self, reminder_id: int):
        with self._connect() as conn:
            conn.execute("UPDATE reminders SET fired=1 WHERE id=?", (reminder_id,))

    def snooze_reminder(self, reminder_id: int, new_remind_at: datetime):
        new_utc = new_remind_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with self._connect() as conn:
            conn.execute(
                "UPDATE reminders SET remind_at=?, fired=0, snoozed=snoozed+1 WHERE id=?",
                (new_utc, reminder_id),
            )

    def cancel_reminder(self, user_id: int, task_name_fragment: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, task_name FROM reminders WHERE user_id=? AND fired=0 AND task_name LIKE ?",
                (user_id, f"%{task_name_fragment}%"),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM reminders WHERE id=?", (row["id"],))
            return row["task_name"]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_weekly_completions(self, user_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT date(completed_at) as day, COUNT(*) as count
                   FROM completed_tasks
                   WHERE user_id=? AND completed_at >= datetime('now', '-7 days')
                   GROUP BY day ORDER BY day ASC""",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_completion_streak(self, user_id: int) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT date(completed_at) as day FROM completed_tasks WHERE user_id=? ORDER BY day DESC",
                (user_id,),
            ).fetchall()
        if not rows:
            return 0
        streak = 0
        today = date.today()
        for i, row in enumerate(rows):
            expected = (today - timedelta(days=i)).isoformat()
            if row["day"] == expected:
                streak += 1
            else:
                break
        return streak

    def get_total_completed(self, user_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM completed_tasks WHERE user_id=?", (user_id,)
            ).fetchone()
            return row["cnt"] if row else 0
