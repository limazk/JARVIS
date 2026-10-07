"""Vercel plugin via CLI para inspeção de projetos/deployments."""
from __future__ import annotations

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability
from plugins.utils import command_status, run_command


def _list(path: str = ".", **_: object):
    return run_command(["vercel", "list"], cwd=path, timeout=120)


def _inspect(url_or_deployment: str, path: str = ".", **_: object):
    return run_command(["vercel", "inspect", url_or_deployment], cwd=path, timeout=120)


def register_plugins(registry) -> None:
    registry.register(Plugin(
        "vercel", "Vercel", "dev", "Inspeção de projetos e deployments Vercel",
        {
            "deployments.list": PluginCapability(
                "deployments.list", "Lista deployments do projeto.",
                {"type":"object","properties":{"path":{"type":"string"}}},
                RiskLevel.LOW, _list,
            ),
            "deployment.inspect": PluginCapability(
                "deployment.inspect", "Inspeciona um deployment.",
                {"type":"object","properties":{"url_or_deployment":{"type":"string"},"path":{"type":"string"}},"required":["url_or_deployment"]},
                RiskLevel.LOW, _inspect,
            ),
        },
        lambda: command_status("vercel"),
        tags=("deploy","frontend","hosting"),
    ))
