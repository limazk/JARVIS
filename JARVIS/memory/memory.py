"""
Memória de longo prazo — seções 29 e 30 do spec.

Fatos que o usuário pede para o Jarvis guardar ("lembra que meu
editor é o VS Code") ficam na tabela `memories` e sobrevivem entre
execuções — diferente de core/context.py, que é só RAM da sessão
atual e reinicia a cada `python main.py`.

Recuperação: não é um RAG sofisticado com embeddings/vetores — é
busca por palavra-chave (LIKE) nas colunas key/value. Suficiente
para o volume de dados de um assistente pessoal; um banco vetorial
de verdade é item de roadmap (seção 48).

Este módulo também registra duas Tools (remember_fact/list_memories)
para o usuário poder pedir isso explicitamente, e expõe
`recall_relevant`, usada pelo router (core/router.py) para injetar
memórias relevantes no contexto do LLM sem mandar o histórico
inteiro.
"""
from __future__ import annotations

import re

from core.permissions import RiskLevel
from memory.database import get_connection
from tools.base import Tool, ToolResult

_STOPWORDS = {
    "o", "a", "os", "as", "de", "da", "do", "das", "dos", "que", "é", "meu", "minha",
    "meus", "minhas", "um", "uma", "e", "para", "com", "em", "no", "na",
}


def _extract_key(fact: str) -> str:
    words = [w for w in re.findall(r"\w+", fact.lower()) if w not in _STOPWORDS]
    return " ".join(words[:4]) if words else fact.strip().lower()[:40]


def remember_fact(fact: str, **_: object) -> ToolResult:
    """
    Guarda um fato na memória de longo prazo.

    Não duplica: se o mesmo fato (ignorando maiúsculas/espaços) já foi
    guardado antes, não insere de novo — isso evita que a lista de
    memórias fique enchendo de repetições quando o usuário menciona a
    mesma coisa em conversas diferentes (parte do pedido de "guardar
    bem as informações", seção 29/30 do spec). Quando o usuário atualiza
    um fato (ex.: "moro em Curitiba" e depois "moro em São Paulo"), as
    duas linhas ficam guardadas, mas `recall_relevant` devolve a mais
    recente primeiro (ORDER BY id DESC), então a informação atual sempre
    aparece antes da desatualizada.
    """
    key = _extract_key(fact)
    clean_fact = fact.strip()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM memories WHERE value = ? COLLATE NOCASE LIMIT 1", (clean_fact,)
        ).fetchone()
        if existing is not None:
            return ToolResult(success=True, message="Já sabia disso — mantido.", data={"key": key})
        conn.execute("INSERT INTO memories (key, value) VALUES (?, ?)", (key, clean_fact))
    return ToolResult(success=True, message="Vou lembrar disso.", data={"key": key})


def recall_relevant(query: str, limit: int = 5) -> list[str]:
    """Usado pelo router para injetar contexto relevante antes de chamar o LLM (busca por palavra-chave)."""
    words = [w for w in re.findall(r"\w+", query.lower()) if w not in _STOPWORDS and len(w) > 2]
    if not words:
        return []
    with get_connection() as conn:
        clauses = " OR ".join(["value LIKE ?"] * len(words))
        params = [f"%{w}%" for w in words]
        rows = conn.execute(
            f"SELECT value FROM memories WHERE {clauses} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [row["value"] for row in rows]


def list_memories(**_: object) -> ToolResult:
    with get_connection() as conn:
        rows = conn.execute("SELECT value FROM memories ORDER BY id DESC LIMIT 20").fetchall()
    if not rows:
        return ToolResult(success=True, message="Ainda não guardei nenhuma informação sobre você.")
    listed = "\n".join(f"- {r['value']}" for r in rows)
    return ToolResult(success=True, message=f"O que eu sei:\n{listed}")


def register(registry) -> None:
    registry.register(Tool(
        name="remember_fact",
        description="Guarda um fato ou preferência do usuário na memória de longo prazo (ex.: 'meu editor é o VS Code').",
        parameters={"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]},
        risk_level=RiskLevel.LOW,
        handler=remember_fact,
        confirmation_template="Lembrar: {fact}",
    ))
    registry.register(Tool(
        name="list_memories",
        description="Lista as informações que o Jarvis guardou sobre o usuário.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=list_memories,
    ))
