"""
Conexão e schema do banco SQLite do Jarvis — seção 29 do spec.

Um único arquivo (database/jarvis.db) guarda tudo: conversas,
memórias de longo prazo, preferências, notas, lembretes e o log de
atividades. Este módulo é a única porta de entrada para o banco —
tools/notes.py, tools/reminders.py e memory/*.py usam get_connection()
em vez de abrir conexões próprias, então o schema fica centralizado
aqui.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from config.settings import settings

_lock = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


def _db_path() -> Path:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings.db_path


def init_db() -> None:
    with _lock, sqlite3.connect(_db_path()) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@contextmanager
def get_connection():
    """Context manager: `with get_connection() as conn: conn.execute(...)`."""
    init_db()
    with _lock:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def log_activity(description: str) -> None:
    """Registra uma linha no painel de ATIVIDADE (seção 10/55)."""
    with get_connection() as conn:
        conn.execute("INSERT INTO activities (description) VALUES (?)", (description,))


def recent_activities(limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM activities ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
