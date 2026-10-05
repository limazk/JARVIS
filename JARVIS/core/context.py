"""
Memória de curto prazo (short-term memory) — seção 30 do spec.

Guarda apenas as últimas N mensagens da conversa atual, em RAM.
Isso é o que vai para o LLM como contexto — nunca o histórico
inteiro. A memória de longo prazo (fatos que sobrevivem entre
execuções) fica em memory/memory.py, usando SQLite (ETAPA 4).
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
    """Buffer circular com as últimas `max_messages` mensagens da sessão atual."""

    def __init__(self, max_messages: int = 12) -> None:
        self.max_messages = max_messages
        self._buffer: Deque[Message] = deque(maxlen=max_messages)

    def add(self, role: Role, content: str) -> None:
        self._buffer.append(Message(role=role, content=content))

    def recent(self) -> list[Message]:
        return list(self._buffer)

    def as_llm_messages(self) -> list[dict]:
        """Formato aceito pelas APIs de LLM (role/content), sem mensagens 'system'."""
        return [{"role": m.role, "content": m.content} for m in self._buffer if m.role != "system"]

    def clear(self) -> None:
        self._buffer.clear()
