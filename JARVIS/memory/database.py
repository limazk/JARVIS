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
_initialized_paths: set[Path] = set()
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
    path = _db_path()
    # CREATE TABLE/FTS5/TRIGGER custa mais que uma consulta simples: execute
    # apenas uma vez por processo e por caminho de banco (testes usam tmp DBs).
    with _lock:
        if path in _initialized_paths and path.exists():
            return
        with sqlite3.connect(path) as conn:
            _initialize_schema(conn)
        _initialized_paths.add(path)


def _initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    # Índice FTS5 opcional com sincronização por triggers. Recria conteúdo
    # existente somente na primeira migração; instalações sem FTS5 seguem
    # funcionando via LIKE.
    try:
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'memories_fts'"
        ).fetchone() is not None
        conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                key, value, content='memories', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TRIGGER IF NOT EXISTS memories_fts_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, key, value)
                VALUES (new.id, new.key, new.value);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_fts_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, key, value)
                VALUES ('delete', old.id, old.key, old.value);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_fts_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, key, value)
                VALUES ('delete', old.id, old.key, old.value);
                INSERT INTO memories_fts(rowid, key, value)
                VALUES (new.id, new.key, new.value);
            END;
        """)
        if not existed:
            conn.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
    except sqlite3.OperationalError:
        pass
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
