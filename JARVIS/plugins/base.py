"""Primitivas da arquitetura de plugins."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from core.permissions import RiskLevel


@dataclass
class PluginResult:
    success: bool
    message: str
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PluginStatus:
    available: bool
    detail: str = ""


Handler = Callable[..., PluginResult]
StatusFn = Callable[[], PluginStatus]


@dataclass
class PluginCapability:
    name: str
    description: str
    parameters: dict
    risk_level: RiskLevel
    handler: Handler
    confirmation_template: str | None = None

    def describe_action(self, plugin_name: str, **kwargs: Any) -> str:
        if self.confirmation_template:
            try:
                return self.confirmation_template.format(**kwargs)
            except Exception:
                pass
        return f"{plugin_name}.{self.name}({kwargs})"

    def execute(self, **kwargs: Any) -> PluginResult:
        try:
            return self.handler(**kwargs)
        except Exception as exc:
            return PluginResult(False, f"Erro em '{self.name}': {exc}")


@dataclass
class Plugin:
    id: str
    name: str
    category: str
    description: str
    capabilities: dict[str, PluginCapability]
    status_fn: StatusFn
    tags: tuple[str, ...] = ()

    def status(self) -> PluginStatus:
        try:
            return self.status_fn()
        except Exception as exc:
            return PluginStatus(False, f"falha ao verificar: {exc}")

    def capability(self, name: str) -> PluginCapability | None:
        return self.capabilities.get(name)

    def compact_catalog(self) -> str:
        actions = ",".join(self.capabilities.keys())
        return f"{self.id}[{actions}]"
