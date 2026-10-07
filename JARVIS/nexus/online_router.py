"""Roteador online econômico do NEXUS.

A regra principal é: NÃO gastar tokens quando a decisão local já é clara.
Quando a tarefa é ambígua, usa uma cadeia curta de verificadores online,
com contexto mínimo e saída JSON minúscula.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace

from nexus.providers import ProviderRun, discover, run_api_provider
from nexus.router import RoutingDecision


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _chain() -> tuple[str, ...]:
    raw = os.getenv(
        "NEXUS_ROUTER_CHAIN",
        "grok,mistral",
    )
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^\`\`\`(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*\`\`\`$", "", text)
    return text.strip()


def parse_router_json(text: str) -> dict:
    """Extrai um objeto JSON mesmo se o modelo acrescentar cerca."""
    clean = _strip_fence(text)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _router_prompt(task: str, available: list[str], local: RoutingDecision) -> str:
    max_chars = max(300, _int("NEXUS_ROUTER_MAX_INPUT_CHARS", 1600))
    task = task[:max_chars]
    routes = ", ".join(available)
    return (
        "TAREFA:\n"
        f"{task}\n\n"
        f"DECISAO_LOCAL: kind={local.kind}; route={local.provider}; confidence={local.confidence:.2f}\n"
        f"ROTAS_DISPONIVEIS: {routes}\n\n"
        "Escolha UMA rota. Regras: jarvis=tools/memoria/ROTINA/acoes locais; "
        "codex=editar/testar codigo no terminal; claude=terminal+codigo+raciocinio; "
        "gemini_cli=terminal; gemini/groq/openrouter/mistral/together/cloudflare/cerebras="
        "IA online de texto, planejamento, classificacao e revisao; ollama=IA local. "
        "Para tarefa que exige alterar arquivos, prefira codex/claude/gemini_cli/jarvis. "
        "Para tarefa simples/local, prefira jarvis. Economize chamadas premium.\n"
        "Responda SOMENTE JSON em uma linha: "
        '{"route":"nome","kind":"code|review|research|general|jarvis_tool",'
        '"confidence":0.0,"needs_ai":true,"reason":"max 8 palavras"}'
    )


@dataclass(frozen=True)
class OnlineRouterResult:
    decision: RoutingDecision
    calls: int
    prompt_tokens: int
    completion_tokens: int
    providers_used: tuple[str, ...]


def _normalize_decision(
    data: dict,
    *,
    fallback: RoutingDecision,
    availability: dict[str, bool],
    verifier: str,
    usage: ProviderRun,
) -> RoutingDecision:
    route = str(data.get("route") or fallback.provider).strip().lower()
    if route == "local":
        route = "jarvis"
    if not availability.get(route, False):
        route = fallback.provider

    kind = str(data.get("kind") or fallback.kind).strip().lower()
    if kind not in {"code", "review", "research", "general", "jarvis_tool"}:
        kind = fallback.kind

    try:
        confidence = float(data.get("confidence", fallback.confidence))
    except (TypeError, ValueError):
        confidence = fallback.confidence
    confidence = max(0.0, min(1.0, confidence))

    reason = str(data.get("reason") or "verificação online")[:120]
    return RoutingDecision(
        provider=route,
        kind=kind,
        confidence=confidence,
        source="online",
        reason=reason,
        verifier=verifier,
        plugins=fallback.plugins,
        router_prompt_tokens=usage.prompt_tokens,
        router_completion_tokens=usage.completion_tokens,
    )


def verify_route(
    prompt: str,
    local: RoutingDecision,
    availability: dict[str, bool],
) -> OnlineRouterResult:
    """Confirma/ajusta uma rota usando APENAS Grok/Mistral como identificadores.

    Nenhum outro worker é usado para classificar. A segunda IA identificadora
    só entra se a primeira falhar ou devolver baixa confiança.
    """
    enabled = _bool("NEXUS_ONLINE_ROUTER", True)
    verify_always = _bool("NEXUS_ROUTER_VERIFY_ALWAYS", False)
    threshold = _float("NEXUS_ROUTER_CONFIDENCE", 0.85)

    # Intents locais do JARVIS nunca precisam pagar uma verificação online.
    if not enabled or local.kind == "jarvis_tool":
        return OnlineRouterResult(local, 0, 0, 0, ())
    if not verify_always and local.confidence >= threshold:
        return OnlineRouterResult(local, 0, 0, 0, ())

    providers = discover()
    available_routes = [
        name for name, ok in availability.items()
        if ok and (
            name == "jarvis"
            or (name in providers and not providers[name].routing_only)
        )
    ]
    router_candidates = [
        name for name in _chain()
        if availability.get(name, False)
        and name in providers
        and providers[name].transport == "api"
        and providers[name].routing_only
    ]
    if not router_candidates:
        return OnlineRouterResult(local, 0, 0, 0, ())

    prompt_tokens = 0
    completion_tokens = 0
    calls = 0
    used: list[str] = []
    first: RoutingDecision | None = None

    max_calls = max(1, _int("NEXUS_ROUTER_MAX_CALLS", 3))
    for verifier in router_candidates[:max_calls]:
        request = _router_prompt(prompt, available_routes, local)
        run = run_api_provider(
            verifier,
            request,
            max_tokens=max(32, _int("NEXUS_ROUTER_MAX_OUTPUT_TOKENS", 96)),
            router_mode=True,
        )
        calls += 1
        used.append(verifier)
        prompt_tokens += run.prompt_tokens
        completion_tokens += run.completion_tokens
        if not run.ok:
            continue

        try:
            data = parse_router_json(run.text)
        except (ValueError, TypeError, json.JSONDecodeError):
            continue

        decision = _normalize_decision(
            data,
            fallback=local,
            availability=availability,
            verifier=verifier,
            usage=run,
        )

        if first is None:
            first = decision
            if decision.confidence >= threshold:
                return OnlineRouterResult(
                    replace(
                        decision,
                        router_prompt_tokens=prompt_tokens,
                        router_completion_tokens=completion_tokens,
                    ),
                    calls,
                    prompt_tokens,
                    completion_tokens,
                    tuple(used),
                )
            continue

        # Consenso entre duas IAs: rota igual ganha confiança.
        if decision.provider == first.provider and decision.kind == first.kind:
            consensus = replace(
                decision,
                confidence=max(decision.confidence, first.confidence, threshold),
                source="online_consensus",
                verifier="+".join(used),
                reason=f"consenso: {decision.reason}"[:120],
                router_prompt_tokens=prompt_tokens,
                router_completion_tokens=completion_tokens,
            )
            return OnlineRouterResult(
                consensus, calls, prompt_tokens, completion_tokens, tuple(used)
            )

        # Discordância: usa a decisão de maior confiança; empate favorece a local
        # para evitar gastar mais tokens tentando desempatar.
        best = max((local, first, decision), key=lambda item: item.confidence)
        best = replace(
            best,
            source="online_disagreement" if best is not local else local.source,
            verifier="+".join(used) if best is not local else local.verifier,
            router_prompt_tokens=prompt_tokens,
            router_completion_tokens=completion_tokens,
        )
        return OnlineRouterResult(best, calls, prompt_tokens, completion_tokens, tuple(used))

    if first is not None:
        first = replace(
            first,
            router_prompt_tokens=prompt_tokens,
            router_completion_tokens=completion_tokens,
        )
        return OnlineRouterResult(first, calls, prompt_tokens, completion_tokens, tuple(used))
    return OnlineRouterResult(
        replace(
            local,
            router_prompt_tokens=prompt_tokens,
            router_completion_tokens=completion_tokens,
        ),
        calls,
        prompt_tokens,
        completion_tokens,
        tuple(used),
    )
