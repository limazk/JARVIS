"""Roteamento local do NEXUS.

O NEXUS usa o próprio parser de intenções do JARVIS antes de escolher
um worker externo. Assim, ações pessoais/locais continuam passando por
memória, permissões e ToolRegistry do JARVIS.
"""
from __future__ import annotations

from core.intent import match_local_intent

_CODE_WORDS = (
    "código", "codigo", "bug", "python", "javascript", "typescript", "react",
    "api", "backend", "frontend", "refator", "teste", "função", "funcao",
    "classe", "repo", "repositório", "repositorio", "implementar", "commit",
    "deploy", "docker", "sql", "css", "html",
)
_REVIEW_WORDS = (
    "revise", "revisar", "review", "audite", "auditar", "segurança", "seguranca",
    "analise o código", "analise o codigo", "code review", "vulnerabilidade",
)
_RESEARCH_WORDS = (
    "pesquise", "pesquisar", "pesquisa", "documentação", "documentacao",
    "referências", "referencias", "compare", "mercado", "notícias", "noticias",
    "fontes", "artigo",
)


def classify(prompt: str) -> str:
    """Classifica sem gastar tokens."""
    text = prompt.lower()
    if any(word in text for word in _REVIEW_WORDS):
        return "review"
    if any(word in text for word in _CODE_WORDS):
        return "code"
    if any(word in text for word in _RESEARCH_WORDS):
        return "research"
    return "general"


def choose_provider(prompt: str, availability: dict[str, bool]) -> tuple[str, str]:
    """Escolhe o executor.

    Qualquer intenção local reconhecida pelo JARVIS fica no próprio JARVIS,
    preservando tools, permissões, ROTINA e memória. Tarefas pesadas podem
    ser delegadas aos CLIs externos.
    """
    local_intent = match_local_intent(prompt)
    if local_intent.matched:
        return "jarvis", "jarvis_tool"

    kind = classify(prompt)
    priorities = {
        "code": ("codex", "claude", "gemini", "ollama", "jarvis"),
        "review": ("claude", "codex", "gemini", "ollama", "jarvis"),
        "research": ("gemini", "claude", "jarvis", "ollama", "codex"),
        "general": ("jarvis", "claude", "gemini", "ollama", "codex"),
    }
    for provider in priorities[kind]:
        if availability.get(provider, False):
            return provider, kind
    return "jarvis", kind
