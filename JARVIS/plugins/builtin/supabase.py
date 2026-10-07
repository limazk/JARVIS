"""Supabase plugin via CLI, focado em inspeção segura."""
from __future__ import annotations

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability
from plugins.utils import command_status, run_command


def _projects(**_: object):
    return run_command(["supabase", "projects", "list"], timeout=90)


def _migration_list(path: str = ".", **_: object):
    return run_command(["supabase", "migration", "list"], cwd=path, timeout=90)


def _functions_list(path: str = ".", **_: object):
    return run_command(["supabase", "functions", "list"], cwd=path, timeout=90)


def register_plugins(registry) -> None:
    registry.register(Plugin(
        "supabase", "Supabase", "dev", "Projetos, migrations e funções Supabase",
        {
            "projects.list": PluginCapability(
                "projects.list", "Lista projetos Supabase acessíveis.",
                {"type":"object","properties":{}}, RiskLevel.LOW, _projects,
            ),
            "migrations.list": PluginCapability(
                "migrations.list", "Lista migrations do projeto.",
                {"type":"object","properties":{"path":{"type":"string"}}},
                RiskLevel.LOW, _migration_list,
            ),
            "functions.list": PluginCapability(
                "functions.list", "Lista Edge Functions do projeto.",
                {"type":"object","properties":{"path":{"type":"string"}}},
                RiskLevel.LOW, _functions_list,
            ),
        },
        lambda: command_status("supabase"),
        tags=("database","postgres","auth","backend"),
    ))
