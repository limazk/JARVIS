"""Notion REST API — documentação e conhecimento."""
from __future__ import annotations

import os

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability, PluginStatus
from plugins.utils import request_json

_BASE = "https://api.notion.com/v1"


def _token():
    return (os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN") or "").strip()


def _headers():
    return {
        "Authorization": f"Bearer {_token()}",
        "Notion-Version": os.getenv("NOTION_API_VERSION", "2022-06-28"),
        "Content-Type": "application/json",
    }


def _status():
    token = _token()
    return PluginStatus(bool(token), "API configurada" if token else "configure NOTION_API_KEY")


def _search(query: str = "", page_size: int = 20, **_: object):
    body = {"page_size": max(1, min(page_size, 100))}
    if query:
        body["query"] = query
    return request_json("POST", f"{_BASE}/search", headers=_headers(), json_body=body)


def _page_get(page_id: str, **_: object):
    return request_json("GET", f"{_BASE}/pages/{page_id}", headers=_headers())


def _page_create(parent_page_id: str, title: str, content: str = "", **_: object):
    body = {
        "parent": {"page_id": parent_page_id},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
    }
    if content:
        body["children"] = [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": content[:1900]}}]
            },
        }]
    return request_json("POST", f"{_BASE}/pages", headers=_headers(), json_body=body)


def _append(page_id: str, content: str, **_: object):
    body = {
        "children": [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": content[:1900]}}]
            },
        }]
    }
    return request_json(
        "PATCH", f"{_BASE}/blocks/{page_id}/children",
        headers=_headers(), json_body=body,
    )


def register_plugins(registry) -> None:
    registry.register(Plugin(
        "notion", "Notion", "productivity",
        "Documentação, wiki, páginas e conhecimento do workspace",
        {
            "search": PluginCapability(
                "search", "Busca páginas e objetos no Notion.",
                {"type":"object","properties":{"query":{"type":"string"},"page_size":{"type":"integer"}}},
                RiskLevel.LOW, _search,
            ),
            "page.get": PluginCapability(
                "page.get", "Lê metadados de uma página.",
                {"type":"object","properties":{"page_id":{"type":"string"}},"required":["page_id"]},
                RiskLevel.LOW, _page_get,
            ),
            "page.create": PluginCapability(
                "page.create", "Cria uma página filha com título e texto inicial.",
                {"type":"object","properties":{"parent_page_id":{"type":"string"},"title":{"type":"string"},"content":{"type":"string"}},"required":["parent_page_id","title"]},
                RiskLevel.MEDIUM, _page_create, "Criar página Notion '{title}'",
            ),
            "page.append": PluginCapability(
                "page.append", "Adiciona um parágrafo a uma página.",
                {"type":"object","properties":{"page_id":{"type":"string"},"content":{"type":"string"}},"required":["page_id","content"]},
                RiskLevel.MEDIUM, _append, "Adicionar conteúdo à página Notion {page_id}",
            ),
        },
        _status,
        tags=("docs","knowledge","wiki","tasks"),
    ))
