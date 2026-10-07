"""Trello REST API."""
from __future__ import annotations

import os

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability
from plugins.utils import env_status, request_json

_BASE = "https://api.trello.com/1"


def _auth():
    return {
        "key": os.getenv("TRELLO_API_KEY", "").strip(),
        "token": os.getenv("TRELLO_TOKEN", "").strip(),
    }


def _boards(**_: object):
    return request_json(
        "GET", f"{_BASE}/members/me/boards",
        params={**_auth(), "fields": "name,url,closed"},
    )


def _cards(board_id: str, **_: object):
    return request_json(
        "GET", f"{_BASE}/boards/{board_id}/cards",
        params={**_auth(), "fields": "name,idList,url,due"},
    )


def _create_card(list_id: str, name: str, description: str = "", due: str = "", **_: object):
    params = {**_auth(), "idList": list_id, "name": name, "desc": description}
    if due:
        params["due"] = due
    return request_json("POST", f"{_BASE}/cards", params=params)


def _move_card(card_id: str, list_id: str, **_: object):
    return request_json(
        "PUT", f"{_BASE}/cards/{card_id}",
        params={**_auth(), "idList": list_id},
    )


def register_plugins(registry) -> None:
    registry.register(Plugin(
        "trello", "Trello", "productivity", "Boards, cards e fluxo Kanban",
        {
            "boards.list": PluginCapability(
                "boards.list", "Lista boards do usuário.",
                {"type":"object","properties":{}}, RiskLevel.LOW, _boards,
            ),
            "cards.list": PluginCapability(
                "cards.list", "Lista cards de um board.",
                {"type":"object","properties":{"board_id":{"type":"string"}},"required":["board_id"]},
                RiskLevel.LOW, _cards,
            ),
            "card.create": PluginCapability(
                "card.create", "Cria card em uma lista.",
                {"type":"object","properties":{"list_id":{"type":"string"},"name":{"type":"string"},"description":{"type":"string"},"due":{"type":"string"}},"required":["list_id","name"]},
                RiskLevel.MEDIUM, _create_card, "Criar card Trello '{name}'",
            ),
            "card.move": PluginCapability(
                "card.move", "Move card para outra lista.",
                {"type":"object","properties":{"card_id":{"type":"string"},"list_id":{"type":"string"}},"required":["card_id","list_id"]},
                RiskLevel.MEDIUM, _move_card, "Mover card Trello {card_id}",
            ),
        },
        lambda: env_status("TRELLO_API_KEY", "TRELLO_TOKEN", detail="API configurada"),
        tags=("kanban","tasks","project"),
    ))
