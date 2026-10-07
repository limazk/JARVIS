"""Ponte entre PluginRegistry e ToolRegistry do JARVIS."""
from __future__ import annotations

import json

from core.permissions import RiskLevel
from plugins.registry import build_default_plugin_registry
from tools.base import Tool, ToolResult


def attach_plugin_registry(tool_registry, permissions=None):
    plugins = build_default_plugin_registry(tool_registry, permissions)
    tool_registry.plugin_registry = plugins

    def list_plugins(category: str = "", available_only: bool = False, **_: object) -> ToolResult:
        rows = plugins.status_rows()
        if category:
            rows = [row for row in rows if row["category"].lower() == category.lower()]
        if available_only:
            rows = [row for row in rows if row["available"]]
        if not rows:
            return ToolResult(True, "Nenhum plugin encontrado.", {"plugins": []})
        lines = [
            f"- {r['id']}: {'online' if r['available'] else 'offline'} · {r['category']} · "
            f"{', '.join(r['capabilities'])}"
            for r in rows
        ]
        return ToolResult(True, "Plugins:\n" + "\n".join(lines), {"plugins": rows})

    def plugin_status(plugin: str, **_: object) -> ToolResult:
        item = plugins.get(plugin)
        if item is None:
            return ToolResult(False, f"Plugin desconhecido: {plugin}")
        status = item.status()
        return ToolResult(
            status.available,
            f"{item.name}: {'disponível' if status.available else 'indisponível'} — {status.detail}",
            {
                "id": item.id,
                "category": item.category,
                "capabilities": list(item.capabilities),
                "available": status.available,
            },
        )

    def plugin_execute(plugin: str, action: str, arguments: dict | str | None = None, **_: object) -> ToolResult:
        args = arguments
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                return ToolResult(False, "arguments precisa ser JSON válido.")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return ToolResult(False, "arguments precisa ser um objeto.")
        result = plugins.invoke(plugin, action, args)
        return ToolResult(result.success, result.message, result.data)

    tool_registry.register(Tool(
        name="list_plugins",
        description="Lista plugins do JARVIS/NEXUS e suas capacidades. Use para descobrir integrações externas disponíveis.",
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "available_only": {"type": "boolean"},
            },
        },
        risk_level=RiskLevel.LOW,
        handler=list_plugins,
    ))
    tool_registry.register(Tool(
        name="plugin_status",
        description="Mostra status, categoria e ações disponíveis de um plugin específico.",
        parameters={
            "type": "object",
            "properties": {"plugin": {"type": "string"}},
            "required": ["plugin"],
        },
        risk_level=RiskLevel.LOW,
        handler=plugin_status,
    ))
    tool_registry.register(Tool(
        name="plugin_execute",
        description=(
            "Executa uma ação de um plugin. Antes use list_plugins/plugin_status se não souber "
            "o nome exato da ação. As permissões reais são verificadas internamente por ação."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plugin": {"type": "string"},
                "action": {"type": "string"},
                "arguments": {"type": "object", "additionalProperties": True},
            },
            "required": ["plugin", "action"],
        },
        risk_level=RiskLevel.LOW,
        handler=plugin_execute,
    ))
    return plugins
