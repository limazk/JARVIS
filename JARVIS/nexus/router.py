"""Primeiro estágio do roteamento do NEXUS: 100% local e sem tokens."""
from __future__ import annotations

from dataclasses import dataclass

from core.intent import match_local_intent

_CODE_WORDS = (
    "código", "codigo", "bug", "python", "javascript", "typescript", "react",
    "api", "backend", "frontend", "refator", "teste", "função", "funcao",
    "classe", "repo", "repositório", "repositorio", "implementar", "commit",
    "deploy", "docker", "sql", "css", "html", "pytest", "endpoint",
)
_REVIEW_WORDS = (
    "revise", "revisar", "review", "audite", "auditar", "segurança", "seguranca",
    "analise o código", "analise o codigo", "code review", "vulnerabilidade",
    "qualidade do código", "qualidade do codigo",
)
_RESEARCH_WORDS = (
    "pesquise", "pesquisar", "pesquisa", "documentação", "documentacao",
    "referências", "referencias", "compare", "mercado", "notícias", "noticias",
    "fontes", "artigo", "investigue",
)


@dataclass(frozen=True)
class RoutingDecision:
    provider: str
    kind: str
    confidence: float
    source: str = "local"
    reason: str = ""
    verifier: str = ""
    router_prompt_tokens: int = 0
    router_completion_tokens: int = 0


def _hits(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for word in words if word in text)


def classify(prompt: str) -> str:
    return classify_with_confidence(prompt)[0]


def classify_with_confidence(prompt: str) -> tuple[str, float]:
    """Classifica localmente e estima confiança para decidir se vale usar API."""
    text = prompt.lower()
    scores = {
        "review": _hits(text, _REVIEW_WORDS),
        "code": _hits(text, _CODE_WORDS),
        "research": _hits(text, _RESEARCH_WORDS),
    }
    kind, score = max(scores.items(), key=lambda item: item[1])
    if score <= 0:
        return "general", 0.45
    if score == 1:
        return kind, 0.78
    if score == 2:
        return kind, 0.90
    return kind, 0.97


def _first_available(priority: tuple[str, ...], availability: dict[str, bool]) -> str:
    for provider in priority:
        if availability.get(provider, False):
            return provider
    return "jarvis"


def local_route(prompt: str, availability: dict[str, bool]) -> RoutingDecision:
    """Produz a primeira decisão sem chamar nenhuma IA.

    Comandos já conhecidos pelo JARVIS têm prioridade absoluta e confiança 1.0.
    """
    local_intent = match_local_intent(prompt)
    if local_intent.matched:
        return RoutingDecision(
            provider="jarvis",
            kind="jarvis_tool",
            confidence=1.0,
            source="local_intent",
            reason=f"tool local: {local_intent.tool_name}",
        )

    kind, confidence = classify_with_confidence(prompt)
    priorities = {
        # APIs de texto não são priorizadas para alteração real de arquivos.
        "code": (
            "codex", "claude", "gemini_cli", "jarvis",
            "cerebras", "gemini", "groq", "openrouter",
            "together", "cloudflare", "ollama",
        ),
        # Aqui as IAs online baratas entram cedo, pois review não precisa editar.
        "review": (
            "cerebras", "groq", "gemini", "openrouter",
            "together", "cloudflare", "claude", "ollama", "jarvis",
        ),
        "research": (
            "gemini", "openrouter", "groq", "together",
            "cerebras", "cloudflare", "jarvis", "claude", "ollama",
        ),
        # General fica deliberadamente conservador: a baixa confiança fará
        # o online_router verificar a escolha quando estiver configurado.
        "general": (
            "jarvis", "gemini", "groq", "openrouter",
            "together", "cloudflare", "cerebras", "claude", "ollama",
        ),
    }
    provider = _first_available(priorities[kind], availability)
    return RoutingDecision(
        provider=provider,
        kind=kind,
        confidence=confidence,
        source="local_rules",
        reason=f"{kind}: {confidence:.0%} de confiança local",
    )


def choose_provider(prompt: str, availability: dict[str, bool]) -> tuple[str, str]:
    """Compatibilidade com chamadas antigas/testes."""
    decision = local_route(prompt, availability)
    return decision.provider, decision.kind
