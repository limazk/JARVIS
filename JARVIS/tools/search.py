"""
Pesquisa na internet — seção 14 do spec.

Usa `duckduckgo_search` (grátis, sem necessidade de API key/cadastro)
para trazer uma resposta resumida sobre algo que o modelo não pode
saber sozinho (notícias, preços, eventos recentes). Isso é
diferente de tools/browser.py: aqui o Jarvis lê o resultado e
responde com a informação; o browser.py só abre a página.
"""
from __future__ import annotations

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult


def web_search(query: str, **_: object) -> ToolResult:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return ToolResult(
            success=False,
            message="A busca na internet requer o pacote duckduckgo_search (pip install duckduckgo-search).",
        )

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui pesquisar agora ({exc}).")

    if not results:
        return ToolResult(success=False, message=f"Não encontrei nada sobre '{query}'.")

    top = results[0]
    summary = top.get("body", "").strip()
    source = top.get("href", "")
    message = f"{summary}" + (f" (fonte: {source})" if source else "")
    return ToolResult(success=True, message=message, data={"results": results})


def register(registry) -> None:
    registry.register(Tool(
        name="web_search",
        description=(
            "Pesquisa na internet informações recentes ou que o modelo não sabe de cor "
            "(preços, notícias, eventos atuais). Não usar para conversa comum."
        ),
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        risk_level=RiskLevel.LOW,
        handler=web_search,
        confirmation_template="Pesquisar: {query}",
    ))
