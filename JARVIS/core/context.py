"""Contexto de conversa: janela curta + resumo extrativo dos trechos evictados.

Não chama IA, não inventa fatos e nunca injeta o histórico inteiro no prompt.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Literal

Role = Literal["user", "assistant", "system"]


@dataclass
class Message:
    role: Role
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


class ConversationContext:
    """Buffer de curto prazo com notas compactas, recuperáveis entre reinícios."""

    def __init__(self, max_messages: int = 12, summary_items: int = 8) -> None:
        if max_messages < 2:
            raise ValueError("max_messages deve ser >= 2")
        self.max_messages = max_messages
        self._buffer: Deque[Message] = deque(maxlen=max_messages)
        self._notes: Deque[str] = deque(maxlen=summary_items)

    def add(self, role: Role, content: str) -> None:
        if len(self._buffer) >= self.max_messages:
            old = self._buffer.popleft()
            if old.role in ("user", "assistant"):
                compact = " ".join(old.content.split())[:180]
                if compact:
                    label = "Usuário" if old.role == "user" else "Assistente"
                    self._notes.append(f"{label}: {compact}")
        self._buffer.append(Message(role=role, content=content))

    def recent(self) -> list[Message]:
        return list(self._buffer)

    def as_llm_messages(self) -> list[dict]:
        return [{"role": m.role, "content": m.content}
                for m in self._buffer if m.role != "system"]

    def summary_text(self) -> str:
        """Trechos anteriores de contexto, sem inferências ou instruções novas."""
        return "\n".join(self._notes)

    def restore_summary(self, text: str) -> None:
        self._notes.clear()
        for line in text.splitlines()[-self._notes.maxlen:]:
            line = " ".join(line.split())[:205]
            if line and line.startswith(("Usuário:", "Assistente:")):
                self._notes.append(line)

    def clear(self) -> None:
        self._buffer.clear()
        self._notes.clear()
