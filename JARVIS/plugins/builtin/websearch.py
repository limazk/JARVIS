"""Pesquisa web para agentes: Tavily e Exa."""
from __future__ import annotations

import os

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability
from plugins.utils import env_status, request_json


def _tavily(query: str, max_results: int = 5, search_depth: str = "basic", **_: object):
    body = {
        "api_key": os.getenv("TAVILY_API_KEY", "").strip(),
        "query": query,
        "max_results": max(1, min(max_results, 10)),
        "search_depth": search_depth if search_depth in {"basic", "advanced"} else "basic",
    }
    return request_json("POST", "https://api.tavily.com/search", json_body=body)


def _exa(query: str, num_results: int = 5, **_: object):
    headers = {
        "x-api-key": os.getenv("EXA_API_KEY", "").strip(),
        "Content-Type": "application/json",
    }
    body = {
        "query": query,
        "numResults": max(1, min(num_results, 10)),
        "contents": {"text": {"maxCharacters": 3000}},
    }
    return request_json("POST", "https://api.exa.ai/search", headers=headers, json_body=body)


def register_plugins(registry) -> None:
    registry.register(Plugin(
        "tavily", "Tavily", "web", "Busca web para agentes",
        {
            "search": PluginCapability(
                "search", "Pesquisa a web e retorna resultados estruturados.",
                {"type":"object","properties":{"query":{"type":"string"},"max_results":{"type":"integer"},"search_depth":{"type":"string"}},"required":["query"]},
                RiskLevel.LOW, _tavily,
            )
        },
        lambda: env_status("TAVILY_API_KEY", detail="API configurada"),
        tags=("search","research","web"),
    ))
    registry.register(Plugin(
        "exa", "Exa", "web", "Busca semântica e conteúdo web",
        {
            "search": PluginCapability(
                "search", "Busca páginas e conteúdo com Exa.",
                {"type":"object","properties":{"query":{"type":"string"},"num_results":{"type":"integer"}},"required":["query"]},
                RiskLevel.LOW, _exa,
            )
        },
        lambda: env_status("EXA_API_KEY", detail="API configurada"),
        tags=("search","research","web"),
    ))
