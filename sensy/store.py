"""Storage for SensyGent — mood check-ins, journal, gratitude and chat.

Backed by SQLite, which means: no accounts, no cloud, no cost. The database
lives next to the app (``data/sensygent.db``) unless ``SENSYGENT_DB`` says
otherwise. Everything degrades gracefully to an in-memory database if the
filesystem is read-only (which happens on some free hosts).

Privacy note: when you use a hosted LLM provider, your message text is sent to
that provider to generate a reply. Mood scores, journal entries and gratitude
notes are *only ever* stored locally in this file.
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_DB = "data/sensygent.db"

MOOD_LABELS = {
    1: "Awful", 2: "Very low", 3: "Low", 4: "Below par", 5: "Okay",
    6: "Steady", 7: "Good", 8: "Well", 9: "Great", 10: "Brilliant",
}

MOOD_EMOJI = {
    1: "😞", 2: "😔", 3: "😕", 4: "🙁", 5: "😐",
    6: "🙂", 7: "😊", 8: "😄", 9: "🤩", 10: "🥳",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS mood_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    score       INTEGER NOT NULL,
    emotions    TEXT DEFAULT '',
    note        TEXT DEFAULT '',
    energy      INTEGER DEFAULT 5,
    sleep_hours REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS journal (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    prompt  TEXT DEFAULT '',
    body    TEXT NOT NULL,
    mood    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gratitude (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    body    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    role     TEXT NOT NULL,
    content  TEXT NOT NULL,
    emotion  TEXT DEFAULT '',
    session  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS prefs (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mood_ts  ON mood_entries(ts);
CREATE INDEX IF NOT EXISTS idx_chat_ts  ON chats(ts);
"""


@dataclass
class ChatTurn:
    role: str
    content: str
    emotion: str = ""
    ts: str = ""


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


class Store:
    """Thin, forgiving SQLite wrapper."""

    @staticmethod
    def resolve_path(path: Optional[str] = None) -> str:
        """Where the database lives: explicit path → env var → default."""
        return path or os.environ.get("SENSYGENT_DB") or DEFAULT_DB

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = self.resolve_path(path)
        self.read_only_fallback = False
        self._shared: Optional[sqlite3.Connection] = None
        if self.path != ":memory:":
            try:
                parent = Path(self.path).expanduser().resolve().parent
                parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.path = ":memory:"
                self.read_only_fallback = True
        if self.path == ":memory:":
            # An in-memory database dies with its connection, so keep one alive.
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared.row_factory = sqlite3.Row
        self._init()

    # -- plumbing --------------------------------------------------------- #

    @contextmanager
    def _connect(self):
        if self._shared is not None:
            try:
                yield self._shared
                self._shared.commit()
            except sqlite3.Error:
                self._shared.rollback()
                raise
            return

        connection = sqlite3.connect(self.path, check_same_thread=False, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init(self) -> None:
        try:
            with self._connect() as connection:
                connection.executescript(SCHEMA)
        except sqlite3.DatabaseError:
            self.path = ":memory:"
            self.read_only_fallback = True
            with self._connect() as connection:
                connection.executescript(SCHEMA)

    def _rows(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        with self._connect() as connection:
            return list(connection.execute(sql, params).fetchall())

    def _exec(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self._connect() as connection:
            cursor = connection.execute(sql, params)
            return cursor.lastrowid or 0

    # -- mood ------------------------------------------------------------- #

    def add_mood(
        self,
        score: int,
        emotions: Sequence[str] = (),
        note: str = "",
        energy: int = 5,
        sleep_hours: float = 0.0,
        ts: Optional[str] = None,
    ) -> int:
        return self._exec(
            "INSERT INTO mood_entries (ts, score, emotions, note, energy, sleep_hours) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts or now_iso(), int(score), ",".join(emotions), note, int(energy), float(sleep_hours)),
        )

    def mood_entries(self, limit: int = 400) -> List[sqlite3.Row]:
        return self._rows(
            "SELECT * FROM mood_entries ORDER BY ts DESC LIMIT ?", (limit,)
        )

    def mood_series(self, days: int = 30) -> List[Tuple[str, float]]:
        """Daily average score for the last ``days`` days, oldest first."""
        rows = self._rows(
            "SELECT substr(ts, 1, 10) AS day, AVG(score) AS score "
            "FROM mood_entries GROUP BY day ORDER BY day DESC LIMIT ?",
            (days,),
        )
        return [(row["day"], float(row["score"])) for row in reversed(rows)]

    def latest_mood(self) -> Optional[sqlite3.Row]:
        rows = self._rows("SELECT * FROM mood_entries ORDER BY ts DESC LIMIT 1")
        return rows[0] if rows else None

    def mood_streak(self) -> int:
        days = {row["day"] for row in self._rows("SELECT DISTINCT substr(ts,1,10) AS day FROM mood_entries")}
        streak, cursor = 0, _dt.date.today()
        if cursor.isoformat() not in days:
            cursor = cursor - _dt.timedelta(days=1)
        while cursor.isoformat() in days:
            streak += 1
            cursor -= _dt.timedelta(days=1)
        return streak

    # -- journal ---------------------------------------------------------- #

    def add_journal(self, body: str, prompt: str = "", mood: int = 0) -> int:
        return self._exec(
            "INSERT INTO journal (ts, prompt, body, mood) VALUES (?, ?, ?, ?)",
            (now_iso(), prompt, body, int(mood)),
        )

    def journal_entries(self, limit: int = 100) -> List[sqlite3.Row]:
        return self._rows("SELECT * FROM journal ORDER BY ts DESC LIMIT ?", (limit,))

    def delete_journal(self, entry_id: int) -> None:
        self._exec("DELETE FROM journal WHERE id = ?", (entry_id,))

    # -- gratitude -------------------------------------------------------- #

    def add_gratitude(self, body: str) -> int:
        return self._exec("INSERT INTO gratitude (ts, body) VALUES (?, ?)", (now_iso(), body))

    def gratitude_entries(self, limit: int = 200) -> List[sqlite3.Row]:
        return self._rows("SELECT * FROM gratitude ORDER BY id DESC LIMIT ?", (limit,))

    def delete_gratitude(self, entry_id: int) -> None:
        self._exec("DELETE FROM gratitude WHERE id = ?", (entry_id,))

    # -- chat ------------------------------------------------------------- #

    def add_chat(self, role: str, content: str, emotion: str = "", session: str = "") -> int:
        return self._exec(
            "INSERT INTO chats (ts, role, content, emotion, session) VALUES (?, ?, ?, ?, ?)",
            (now_iso(), role, content, emotion, session),
        )

    def chat_history(self, session: str = "", limit: int = 200) -> List[ChatTurn]:
        if session:
            rows = self._rows(
                "SELECT * FROM chats WHERE session = ? ORDER BY id ASC LIMIT ?",
                (session, limit),
            )
        else:
            rows = list(reversed(self._rows("SELECT * FROM chats ORDER BY id DESC LIMIT ?", (limit,))))
        return [ChatTurn(row["role"], row["content"], row["emotion"] or "", row["ts"]) for row in rows]

    def clear_chat(self, session: str = "") -> None:
        if session:
            self._exec("DELETE FROM chats WHERE session = ?", (session,))
        else:
            self._exec("DELETE FROM chats")

    def sessions(self, limit: int = 20) -> List[sqlite3.Row]:
        return self._rows(
            "SELECT session, MIN(ts) AS started, COUNT(*) AS turns FROM chats "
            "WHERE session != '' GROUP BY session ORDER BY started DESC LIMIT ?",
            (limit,),
        )

    # -- prefs ------------------------------------------------------------ #

    def set_pref(self, key: str, value: str) -> None:
        self._exec(
            "INSERT INTO prefs (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_pref(self, key: str, default: str = "") -> str:
        rows = self._rows("SELECT value FROM prefs WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    # -- analytics --------------------------------------------------------- #

    def stats(self, days: int = 30) -> Dict[str, Any]:
        today = _dt.date.today()
        since = (today - _dt.timedelta(days=days - 1)).isoformat()

        mood_rows = self._rows(
            "SELECT substr(ts,1,10) AS day, AVG(score) AS score, AVG(energy) AS energy "
            "FROM mood_entries WHERE substr(ts,1,10) >= ? GROUP BY day ORDER BY day",
            (since,),
        )
        daily = {row["day"]: float(row["score"]) for row in mood_rows}

        all_scores = [row["score"] for row in self._rows("SELECT score FROM mood_entries")]
        recent_scores = [
            float(row["score"]) for row in self._rows(
                "SELECT score FROM mood_entries WHERE substr(ts,1,10) >= ?", (since,)
            )
        ]

        tags: Dict[str, int] = {}
        for row in self._rows("SELECT emotions FROM mood_entries"):
            for tag in (row["emotions"] or "").split(","):
                tag = tag.strip()
                if tag:
                    tags[tag] = tags.get(tag, 0) + 1

        check_in_days = len({row["day"] for row in mood_rows})
        return {
            "series": daily,
            "average": round(sum(recent_scores) / len(recent_scores), 2) if recent_scores else 0.0,
            "best": max(all_scores) if all_scores else 0,
            "worst": min(all_scores) if all_scores else 0,
            "entries": len(all_scores),
            "check_in_days": check_in_days,
            "streak": self.mood_streak(),
            "tags": dict(sorted(tags.items(), key=lambda kv: kv[1], reverse=True)),
            "journal_count": len(self._rows("SELECT id FROM journal")),
            "gratitude_count": len(self._rows("SELECT id FROM gratitude")),
            "chat_turns": len(self._rows("SELECT id FROM chats WHERE role = 'user'")),
            "days": days,
        }

    def emotion_timeline(self, limit: int = 120) -> List[sqlite3.Row]:
        return self._rows(
            "SELECT substr(ts,1,10) AS day, emotion, COUNT(*) AS n FROM chats "
            "WHERE emotion != '' AND role = 'user' GROUP BY day, emotion ORDER BY day DESC LIMIT ?",
            (limit,),
        )

    def export_text(self) -> str:
        """A plain-text dump of everything — your data stays yours."""
        lines = ["SensyGent export", "=" * 40, ""]
        lines.append("MOOD CHECK-INS")
        for row in reversed(self.mood_entries(1000)):
            lines.append(f"  {row['ts']}  {row['score']}/10  [{row['emotions']}]  {row['note']}")
        lines.append("\nJOURNAL")
        for row in reversed(self.journal_entries(1000)):
            lines.append(f"  {row['ts']}  ({row['prompt']})\n    {row['body']}")
        lines.append("\nGRATITUDE")
        for row in reversed(self.gratitude_entries(1000)):
            lines.append(f"  {row['ts']}  {row['body']}")
        lines.append("\nCONVERSATIONS")
        for turn in self.chat_history(limit=2000):
            who = "You" if turn.role == "user" else "Sensy"
            lines.append(f"  {turn.ts}  {who}: {turn.content}")
        return "\n".join(lines)

    def mood_prompt_context(self, limit: int = 7) -> str:
        """A short summary used to ground the companion in your real history."""
        rows = self.mood_entries(limit)
        if not rows:
            return ""
        scores = [row["score"] for row in rows]
        average = sum(scores) / len(scores)
        tags: Dict[str, int] = {}
        for row in rows:
            for tag in (row["emotions"] or "").split(","):
                tag = tag.strip()
                if tag:
                    tags[tag] = tags.get(tag, 0) + 1
        top = ", ".join(list(dict(sorted(tags.items(), key=lambda kv: -kv[1])))[:4])
        trend = ""
        if len(scores) >= 3:
            first = sum(scores[-3:]) / 3
            last = sum(scores[:3]) / 3
            if last - first > 0.8:
                trend = " They have been trending upward lately."
            elif first - last > 0.8:
                trend = " They have been trending downward lately — be extra gentle."
        return (
            f"Their recent self-reported mood averages {average:.1f}/10 over {len(rows)} check-ins"
            + (f", most often tagged: {top}." if top else ".")
            + trend
        )
