"""Broker para workers externos solicitarem plugins sem receber credenciais."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from plugins.registry import PluginRegistry

_MARKER = re.compile(r"NEXUS_PLUGIN\s*(\{.*?\})(?:\n|$)", re.S)


@dataclass(frozen=True)
class PluginRequest:
    plugin: str
    action: str
    arguments: dict


def extract_requests(text: str, limit: int = 4) -> list[PluginRequest]:
    requests: list[PluginRequest] = []
    for match in _MARKER.finditer(text):
        if len(requests) >= limit:
            break
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        plugin = str(data.get("plugin", "")).strip()
        action = str(data.get("action", "")).strip()
        arguments = data.get("arguments") or {}
        if plugin and action and isinstance(arguments, dict):
            requests.append(PluginRequest(plugin, action, arguments))
    return requests


def describe_plugins(registry: PluginRegistry, plugin_ids: tuple[str, ...] | list[str]) -> str:
    lines = []
    for plugin_id in plugin_ids:
        plugin = registry.get(plugin_id)
        if plugin is None or not plugin.status().available:
            continue
        actions = ", ".join(
            f"{cap.name}: {cap.description[:90]}"
            for cap in plugin.capabilities.values()
        )
        lines.append(f"- {plugin.id}: {actions}")
    if not lines:
        return ""
    return (
        "Plugins disponíveis para esta tarefa:\n"
        + "\n".join(lines)
        + "\nSe precisar executar um plugin, responda com uma linha EXATA no formato "
          'NEXUS_PLUGIN {"plugin":"id","action":"acao","arguments":{}}. '
          "Não inclua credenciais. O NEXUS executará e devolverá o resultado."
    )


def execute_requests(
    registry: PluginRegistry,
    text: str,
    *,
    allowed: set[str] | None = None,
    limit: int = 4,
) -> list[dict]:
    results = []
    for req in extract_requests(text, limit=limit):
        if allowed is not None and req.plugin not in allowed:
            results.append({
                "plugin": req.plugin,
                "action": req.action,
                "success": False,
                "message": "Plugin não autorizado para esta tarefa pelo router.",
                "data": {},
            })
            continue
        result = registry.invoke(req.plugin, req.action, req.arguments)
        results.append({
            "plugin": req.plugin,
            "action": req.action,
            "success": result.success,
            "message": result.message,
            "data": result.data,
        })
    return results
