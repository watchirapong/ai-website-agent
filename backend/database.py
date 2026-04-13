"""SQLite database for project history."""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

from agent.config import DATABASE_PATH

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    scores TEXT DEFAULT '{}',
    lighthouse TEXT DEFAULT '{}',
    deployed_url TEXT,
    attempts INTEGER DEFAULT 0,
    time_seconds REAL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def init_db():
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.execute(_CREATE_TABLE)
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN output_dir TEXT")
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.utcnow().isoformat()


def create_project(prompt: str) -> str:
    project_id = f"proj_{uuid.uuid4().hex[:12]}"
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.execute(
        "INSERT INTO projects (id, prompt, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, prompt, "started", _now(), _now()),
    )
    conn.commit()
    conn.close()
    return project_id


def update_project(project_id: str, **kwargs):
    conn = sqlite3.connect(str(DATABASE_PATH))
    kwargs["updated_at"] = _now()

    for key in ("scores", "lighthouse"):
        if key in kwargs and isinstance(kwargs[key], dict):
            kwargs[key] = json.dumps(kwargs[key])

    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [project_id]
    conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_project(project_id: str) -> dict | None:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    for key in ("scores", "lighthouse"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def list_projects() -> list[dict]:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        for key in ("scores", "lighthouse"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        results.append(d)
    return results


def delete_project(project_id: str) -> bool:
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
