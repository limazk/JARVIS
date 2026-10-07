"""Registro central de plugins.

Plugins são capacidades externas agrupadas por serviço. O registry mantém
credenciais fora do prompt e aplica PermissionManager antes de toda escrita.
"""
from __future__ import annotations

from typing import Optional

from core.permissions import PermissionDenied, PermissionManager
from plugins.base import Plugin, PluginResult


class PluginRegistry:
    def __init__(self, permissions: Optional[PermissionManager] = None) -> None:
        self.permissions = permissions
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin duplicado: {plugin.id}")
        self._plugins[plugin.id] = plugin

    def get(self, plugin_id: str) -> Plugin | None:
        return self._plugins.get(plugin_id)

    def all(self):
        return self._plugins.values()

    def ids(self, *, available_only: bool = False) -> list[str]:
        if not available_only:
            return list(self._plugins)
        return [p.id for p in self._plugins.values() if p.status().available]

    def status_rows(self) -> list[dict]:
        rows = []
        for plugin in self._plugins.values():
            status = plugin.status()
            rows.append({
                "id": plugin.id,
                "name": plugin.name,
                "category": plugin.category,
                "available": status.available,
                "detail": status.detail,
                "capabilities": list(plugin.capabilities),
            })
        return rows

    def compact_catalog(self, *, available_only: bool = True, max_plugins: int = 30) -> str:
        rows = []
        for plugin in self._plugins.values():
            if available_only and not plugin.status().available:
                continue
            rows.append(plugin.compact_catalog())
            if len(rows) >= max_plugins:
                break
        return "; ".join(rows)

    def invoke(self, plugin_id: str, action: str, arguments: dict | None = None) -> PluginResult:
        plugin = self.get(plugin_id)
        if plugin is None:
            return PluginResult(False, f"Plugin desconhecido: {plugin_id}.")

        status = plugin.status()
        if not status.available:
            return PluginResult(False, f"Plugin '{plugin.name}' indisponível: {status.detail}")

        capability = plugin.capability(action)
        if capability is None:
            return PluginResult(
                False,
                f"Plugin '{plugin.name}' não possui a ação '{action}'.",
                {"available_actions": list(plugin.capabilities)},
            )

        args = arguments or {}
        if self.permissions is not None:
            try:
                self.permissions.check(
                    f"plugin:{plugin.id}.{capability.name}",
                    capability.risk_level,
                    capability.describe_action(plugin.name, **args),
                )
            except PermissionDenied as exc:
                return PluginResult(False, str(exc))

        return capability.execute(**args)


def build_default_plugin_registry(tool_registry, permissions=None) -> PluginRegistry:
    registry = PluginRegistry(permissions)

    from plugins.builtin import (
        docker,
        existing,
        notion,
        render,
        services,
        supabase,
        trello,
        vercel,
        websearch,
    )

    existing.register_plugins(registry, tool_registry)
    for module in (docker, supabase, render, vercel, trello, notion, websearch, services):
        module.register_plugins(registry)

    return registry
