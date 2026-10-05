"""
Controle do navegador — seção 13 do spec.

Usa o módulo `webbrowser` da stdlib para abrir o navegador padrão
do Windows — não depende de nenhuma API paga. Para automação
avançada de página (clicar, preencher formulário), o roadmap
(seção 48) prevê integração opcional com Playwright; não implementada
aqui de propósito (foge do escopo de "abrir uma página").

Este módulo também expõe KNOWN_WEBSITES, reaproveitado por
tools/apps.py: quando "abre X" não é um programa instalado, ele
tenta abrir X como site conhecido antes de desistir.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult
from platform_services import get_platform_services

KNOWN_WEBSITES: dict[str, str] = {
    "youtube": "https://youtube.com",
    "github": "https://github.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "netflix": "https://netflix.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "instagram": "https://instagram.com",
    "linkedin": "https://linkedin.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "spotify web": "https://open.spotify.com",
}


def open_website(site: str, **_: object) -> ToolResult:
    key = site.strip().lower()
    url = KNOWN_WEBSITES.get(key)
    if url is None:
        # Se já parece uma URL, usa direto; senão trata como termo de busca.
        url = site if site.startswith(("http://", "https://")) else f"https://{site}"
    result = get_platform_services().open_url(url)
    return ToolResult(result.success, f"Abrindo {site}." if result.success else result.message, {"url": url, **result.data})


def open_browser_search(query: str, **_: object) -> ToolResult:
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    result = get_platform_services().open_url(url)
    return ToolResult(result.success, f"Pesquisando '{query}' no navegador." if result.success else result.message,
                      {"url": url, **result.data})


def register(registry) -> None:
    registry.register(Tool(
        name="open_website",
        description="Abre um site conhecido no navegador padrão (ex.: youtube, github, gmail) ou uma URL.",
        parameters={
            "type": "object",
            "properties": {"site": {"type": "string"}},
            "required": ["site"],
        },
        risk_level=RiskLevel.LOW,
        handler=open_website,
        confirmation_template="Abrir {site} no navegador",
    ))
    registry.register(Tool(
        name="open_browser_search",
        description="Abre o navegador já com uma pesquisa do Google para o termo informado.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        risk_level=RiskLevel.LOW,
        handler=open_browser_search,
    ))
