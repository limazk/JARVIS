"""Memória durável no SQLite: busca relevante por termos/sinônimos e fatos atualizáveis."""
from __future__ import annotations

import re
import unicodedata

from core.permissions import RiskLevel
from memory.database import get_connection
from tools.base import Tool, ToolResult

_STOPWORDS = {
    "o", "a", "os", "as", "de", "da", "do", "das", "dos", "que", "é", "meu", "minha",
    "meus", "minhas", "um", "uma", "e", "para", "com", "em", "no", "na", "eu",
    "qual", "quais", "onde", "quem", "como", "favor", "me", "por", "sobre",
}
_ALIASES = {
    "moro": ("cidade", "residencia", "moradia", "mora"),
    "cidade": ("moro", "residencia", "moradia"),
    "editor": ("vscode", "ide", "codigo"),
    "trabalho": ("emprego", "profissao"),
    "faculdade": ("universidade", "curso"),
    "projeto": ("software", "repositorio"),
    "favorita": ("preferida", "gosto"),
}
_SLOTS = (
    ("residencia", r"\b(?:moro|resido|minha cidade|minha residencia)\b"),
    ("editor", r"\b(?:meu editor|minha ide)\b"),
    ("cor_favorita", r"\b(?:minha cor favorita|cor preferida)\b"),
)
_SECRETS = re.compile(r"\b(senha|password|token secreto|chave de api|api key|cvv|numero do cartao)\b")


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", _normalize(text))
            if len(w) > 2 and w not in _STOPWORDS]


def _slot(text: str) -> str | None:
    normalized = _normalize(text)
    for key, pattern in _SLOTS:
        if re.search(pattern, normalized):
            return key
    return None


def _extract_key(fact: str) -> str:
    slot = _slot(fact)
    if slot:
        return slot
    words = _tokens(fact)
    return " ".join(words[:4]) if words else fact.strip().lower()[:40]


def remember_fact(fact: str, **_: object) -> ToolResult:
    """Salva fatos relevantes e substitui fatos conflitantes em slots reconhecidos."""
    clean = fact.strip()
    if not clean:
        return ToolResult(success=False, message="Não há fato para memorizar.")
    if _SECRETS.search(_normalize(clean)):
        return ToolResult(success=False, message="Não guardo senhas, tokens nem credenciais na memória.")
    key = _extract_key(clean)
    slot = _slot(clean)
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM memories WHERE value = ? COLLATE NOCASE LIMIT 1", (clean,)
        ).fetchone()
        if existing is not None:
            return ToolResult(success=True, message="Já sabia disso — mantido.", data={"key": key})
        if slot:
            rows = conn.execute("SELECT id, value FROM memories ORDER BY id DESC").fetchall()
            # Dados legados também são atualizados sem precisar de migração manual.
            for row in rows:
                if _slot(row["value"]) == slot:
                    conn.execute("DELETE FROM memories WHERE id = ?", (row["id"],))
        conn.execute("INSERT INTO memories (key, value) VALUES (?, ?)", (key, clean))
    return ToolResult(success=True, message="Vou lembrar disso.", data={"key": key})


def recall_relevant(query: str, limit: int = 5) -> list[str]:
    """Busca local (FTS5 quando disponível; fallback LIKE), sem embeddings nem tokens."""
    words = _tokens(query)
    if not words:
        return []
    expanded = set(words)
    for word in words:
        expanded.update(_ALIASES.get(word, ()))
    # Limite defensivo para consultas muito grandes e mantêm o tempo previsível.
    terms = sorted(expanded)[:16]
    candidates = []
    with get_connection() as conn:
        try:
            # FTS5 opcional: ativado apenas em instalações SQLite com suporte.
            match = " OR ".join('"' + word.replace('"', '') + '"' for word in terms)
            candidates = conn.execute(
                "SELECT m.id, m.key, m.value FROM memories_fts f "
                "JOIN memories m ON m.id = f.rowid "
                "WHERE memories_fts MATCH ? LIMIT 250", (match,)
            ).fetchall()
        except Exception:
            # Fallback sem extensão FTS5: pesquisa textual no SQLite normal.
            pass
        if not candidates:
            clauses = " OR ".join(["value LIKE ? OR key LIKE ?"] * len(terms))
            params = [item for word in terms for item in (f"%{word}%", f"%{word}%")]
            candidates = conn.execute(
                f"SELECT id, key, value FROM memories WHERE {clauses} "
                "ORDER BY id DESC LIMIT 250", (*params,)
            ).fetchall()

    ranked = []
    for row in candidates:
        content = set(_tokens(row["key"] + " " + row["value"]))
        overlap = len(content.intersection(expanded))
        if overlap:
            ranked.append((overlap, row["id"], row["value"]))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    result, seen_slots, seen_values = [], set(), set()
    for _, _, value in ranked:
        slot = _slot(value)
        if slot and slot in seen_slots:
            continue
        if value.casefold() in seen_values:
            continue
        result.append(value)
        seen_values.add(value.casefold())
        if slot:
            seen_slots.add(slot)
        if len(result) >= limit:
            break
    return result


def list_memories(**_: object) -> ToolResult:
    with get_connection() as conn:
        rows = conn.execute("SELECT value FROM memories ORDER BY id DESC LIMIT 20").fetchall()
    if not rows:
        return ToolResult(success=True, message="Ainda não guardei nenhuma informação sobre você.")
    return ToolResult(success=True, message="O que eu sei:\n" +
                      "\n".join(f"- {row['value']}" for row in rows))


def forget_fact(fact: str, **_: object) -> ToolResult:
    """Permite remover uma informação explicitamente, sem alterar o histórico de conversas."""
    term = _normalize(fact.strip())
    if len(term) < 3:
        return ToolResult(success=False, message="Informe qual informação devo apagar da memória.")
    count = 0
    with get_connection() as conn:
        rows = conn.execute("SELECT id, key, value FROM memories").fetchall()
        for row in rows:
            if term in _normalize(row["value"]) or term == _normalize(row["key"]):
                conn.execute("DELETE FROM memories WHERE id = ?", (row["id"],))
                count += 1
    return ToolResult(success=True, message=f"{count} memória(s) removida(s).")


def register(registry) -> None:
    registry.register(Tool(
        name="remember_fact",
        description="Guarda uma preferência ou fato duradouro não sensível do usuário.",
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
    registry.register(Tool(
        name="forget_fact",
        description="Remove da memória fatos que contêm o texto indicado pelo usuário.",
        parameters={"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]},
        risk_level=RiskLevel.LOW,
        handler=forget_fact,
    ))
