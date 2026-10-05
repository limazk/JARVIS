"""
Notas — seção 20 do spec.

CRUD simples sobre a tabela `notes` do SQLite (memory/database.py).
"""
from __future__ import annotations

from core.permissions import RiskLevel
from memory.database import get_connection
from tools.base import Tool, ToolResult


def add_note(text: str, **_: object) -> ToolResult:
    with get_connection() as conn:
        conn.execute("INSERT INTO notes (text) VALUES (?)", (text,))
    return ToolResult(success=True, message=f"Nota adicionada: {text}")


def list_notes(**_: object) -> ToolResult:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, text FROM notes ORDER BY id DESC").fetchall()

    if not rows:
        return ToolResult(success=True, message="Você não tem nenhuma nota salva.")

    listed = "\n".join(f"- {row['text']}" for row in rows)
    return ToolResult(success=True, message=f"Suas notas:\n{listed}", data={"notes": [dict(r) for r in rows]})


def remove_note(text: str, **_: object) -> ToolResult:
    with get_connection() as conn:
        cur = conn.execute("SELECT id FROM notes WHERE text LIKE ? ORDER BY id DESC LIMIT 1", (f"%{text}%",))
        row = cur.fetchone()
        if row is None:
            return ToolResult(success=False, message=f"Não achei nenhuma nota parecida com '{text}'.")
        conn.execute("DELETE FROM notes WHERE id = ?", (row["id"],))
    return ToolResult(success=True, message=f"Nota removida: {text}")


def register(registry) -> None:
    registry.register(Tool(
        name="add_note",
        description="Salva uma nota rápida do usuário.",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        risk_level=RiskLevel.LOW,
        handler=add_note,
        confirmation_template="Anotar: {text}",
    ))
    registry.register(Tool(
        name="list_notes",
        description="Lista todas as notas salvas.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=list_notes,
    ))
    registry.register(Tool(
        name="remove_note",
        description="Remove uma nota que combine com o texto informado.",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        risk_level=RiskLevel.MEDIUM,
        handler=remove_note,
        confirmation_template="Remover a nota que contém '{text}'",
    ))
