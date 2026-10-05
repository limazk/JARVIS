"""
Histórico persistido de conversas — seções 29/30 do spec.

Diferente de core/context.py (memória de curto prazo, só RAM da
sessão), este módulo grava cada mensagem no SQLite. Serve de
histórico completo para auditoria/depuração — o que vai para o LLM
continua sendo só o buffer curto do core/context.py, nunca este
histórico inteiro (isso é o que a seção 30 pede: nunca mandar a
conversa inteira para o modelo).
"""
from __future__ import annotations

from memory.database import get_connection


def log_message(role: str, content: str) -> None:
    with get_connection() as conn:
        conn.execute("INSERT INTO conversations (role, content) VALUES (?, ?)", (role, content))


def recent_messages(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]
