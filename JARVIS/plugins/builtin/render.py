"""Render REST API."""
from __future__ import annotations

import os

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability
from plugins.utils import env_status, request_json

_BASE = "https://api.render.com/v1"


def _headers():
    return {
        "Authorization": f"Bearer {os.getenv('RENDER_API_KEY','').strip()}",
        "Accept": "application/json",
    }


def _services(limit: int = 20, **_: object):
    return request_json(
        "GET", f"{_BASE}/services", headers=_headers(),
        params={"limit": max(1, min(limit, 100))},
    )


def _deploys(service_id: str, limit: int = 20, **_: object):
    return request_json(
        "GET", f"{_BASE}/services/{service_id}/deploys", headers=_headers(),
        params={"limit": max(1, min(limit, 100))},
    )


def register_plugins(registry) -> None:
    registry.register(Plugin(
        "render", "Render", "dev", "Serviços, estado e histórico de deploys na Render",
        {
            "services.list": PluginCapability(
                "services.list", "Lista serviços Render.",
                {"type":"object","properties":{"limit":{"type":"integer"}}},
                RiskLevel.LOW, _services,
            ),
            "deploys.list": PluginCapability(
                "deploys.list", "Lista deploys de um serviço.",
                {"type":"object","properties":{"service_id":{"type":"string"},"limit":{"type":"integer"}},"required":["service_id"]},
                RiskLevel.LOW, _deploys,
            ),
        },
        lambda: env_status("RENDER_API_KEY", detail="API configurada"),
        tags=("deploy","backend","hosting"),
    ))
