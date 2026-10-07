"""Docker plugin: inspeção segura de containers e imagens."""
from __future__ import annotations

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability
from plugins.utils import command_status, run_command


def _ps(all: bool = False, **_: object):
    args = ["docker", "ps"]
    if all:
        args.append("-a")
    return run_command(args)


def _images(**_: object):
    return run_command(["docker", "images"])


def _logs(container: str, tail: int = 120, **_: object):
    return run_command(["docker", "logs", "--tail", str(max(1, min(tail, 1000))), container])


def register_plugins(registry) -> None:
    registry.register(Plugin(
        "docker", "Docker", "dev", "Inspeção de containers Docker",
        {
            "containers.list": PluginCapability(
                "containers.list", "Lista containers Docker.",
                {"type":"object","properties":{"all":{"type":"boolean"}}},
                RiskLevel.LOW, _ps,
            ),
            "images.list": PluginCapability(
                "images.list", "Lista imagens Docker.",
                {"type":"object","properties":{}}, RiskLevel.LOW, _images,
            ),
            "logs": PluginCapability(
                "logs", "Mostra logs de um container.",
                {"type":"object","properties":{"container":{"type":"string"},"tail":{"type":"integer"}},"required":["container"]},
                RiskLevel.LOW, _logs,
            ),
        },
        lambda: command_status("docker"),
        tags=("containers","devops"),
    ))
