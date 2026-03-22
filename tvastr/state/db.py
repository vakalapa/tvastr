"""SQLite state store for Tvastr forge sessions."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS sub_objectives (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    description   TEXT NOT NULL,
    status        TEXT DEFAULT 'pending',
    assigned_agent TEXT,
    priority      INTEGER DEFAULT 0,
    depends_on    TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS iterations (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id              TEXT NOT NULL,
    sub_objective_id      INTEGER REFERENCES sub_objectives(id),
    iteration_num         INTEGER NOT NULL,
    hypothesis            TEXT,
    files_changed         TEXT,
    patch_sha             TEXT,
    validate_results      TEXT,
    outcome               TEXT NOT NULL,
    lesson                TEXT,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resource_locks (
    resource    TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS baselines (
    test_name   TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       REAL NOT NULL,
    measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    patch_sha   TEXT,
    PRIMARY KEY (test_name, metric)
);
"""


@dataclass
class Iteration:
    agent_id: str
    sub_objective_id: Optional[int]
    iteration_num: int
    hypothesis: str = ""
    files_changed: list[str] = field(default_factory=list)
    patch_sha: str = ""
    validate_results: Optional[list[dict]] = None
    outcome: str = ""
    lesson: str = ""
    id: Optional[int] = None
    created_at: Optional[str] = None


class StateDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_sub_objective(self, description: str, priority: int = 0, depends_on: list[int] | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO sub_objectives (description, priority, depends_on) VALUES (?, ?, ?)",
                (description, priority, json.dumps(depends_on or [])),
            )
            return cur.lastrowid

    def get_sub_objectives(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM sub_objectives ORDER BY priority DESC").fetchall()
            return [dict(r) for r in rows]

    def update_sub_objective_status(self, obj_id: int, status: str, assigned_agent: str | None = None):
        with self._conn() as conn:
            updates = {"status": status}
            if status == "done":
                updates["completed_at"] = datetime.now().isoformat()
            if assigned_agent is not None:
                updates["assigned_agent"] = assigned_agent
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE sub_objectives SET {set_clause} WHERE id = ?",
                (*updates.values(), obj_id),
            )

    def log_iteration(self, it: Iteration) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO iterations
                   (agent_id, sub_objective_id, iteration_num, hypothesis,
                    files_changed, patch_sha, validate_results,
                    outcome, lesson)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    it.agent_id, it.sub_objective_id, it.iteration_num,
                    it.hypothesis,
                    json.dumps(it.files_changed), it.patch_sha,
                    json.dumps(it.validate_results),
                    it.outcome, it.lesson,
                ),
            )
            return cur.lastrowid

    def get_iterations(self, agent_id: str | None = None, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            if agent_id:
                rows = conn.execute(
                    "SELECT * FROM iterations WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
                    (agent_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM iterations ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_iteration_num(self, agent_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MAX(iteration_num) as max_iter FROM iterations WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            return row["max_iter"] or 0

    def acquire_lock(self, resource: str, agent_id: str, ttl_seconds: int = 600) -> bool:
        with self._conn() as conn:
            now = datetime.now()
            conn.execute(
                "DELETE FROM resource_locks WHERE expires_at < ?",
                (now.isoformat(),),
            )
            try:
                conn.execute(
                    "INSERT INTO resource_locks (resource, agent_id, expires_at) VALUES (?, ?, ?)",
                    (resource, agent_id, (now + timedelta(seconds=ttl_seconds)).isoformat()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def release_lock(self, resource: str, agent_id: str):
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM resource_locks WHERE resource = ? AND agent_id = ?",
                (resource, agent_id),
            )

    def set_baseline(self, test_name: str, metric: str, value: float, patch_sha: str = ""):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO baselines (test_name, metric, value, patch_sha)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (test_name, metric)
                   DO UPDATE SET value = excluded.value, measured_at = CURRENT_TIMESTAMP, patch_sha = excluded.patch_sha""",
                (test_name, metric, value, patch_sha),
            )

    def get_baseline(self, test_name: str, metric: str) -> float | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM baselines WHERE test_name = ? AND metric = ?",
                (test_name, metric),
            ).fetchone()
            return row["value"] if row else None
