"""Adapta Tools já existentes do JARVIS para o sistema de plugins."""
from __future__ import annotations

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability, PluginResult, PluginStatus

# Estas tools já fazem a checagem dinâmica dentro do próprio handler.
_DYNAMIC_PERMISSION_TOOLS = {"git_push", "create_issue", "run_shell_command"}


def _from_tools(
    tool_registry,
    plugin_id: str,
    name: str,
    category: str,
    description: str,
    mapping: dict[str, str],
):
    capabilities = {}
    for action, tool_name in mapping.items():
        tool = tool_registry.get(tool_name)
        if tool is None:
            continue

        def handler(_tool=tool, **kwargs):
            result = _tool.execute(**kwargs)
            return PluginResult(result.success, result.message, result.data)

        risk = RiskLevel.LOW if tool_name in _DYNAMIC_PERMISSION_TOOLS else tool.risk_level
        capabilities[action] = PluginCapability(
            action,
            tool.description,
            tool.parameters,
            risk,
            handler,
            tool.confirmation_template,
        )

    return Plugin(
        plugin_id,
        name,
        category,
        description,
        capabilities,
        lambda: PluginStatus(
            bool(capabilities),
            f"{len(capabilities)} ações registradas; autenticação é verificada na execução",
        ),
        tags=("jarvis-tools",),
    )


def register_plugins(registry, tool_registry) -> None:
    groups = [
        ("github", "GitHub", "dev", "Git/GitHub já integrado ao JARVIS", {
            "status": "git_status",
            "repos.list": "list_my_repos",
            "repo.info": "repo_info",
            "push": "git_push",
            "issue.create": "create_issue",
        }),
        ("filesystem", "Filesystem", "dev", "Arquivos e pastas locais", {
            "folder.open": "open_folder",
            "folder.create": "create_folder",
            "file.find": "find_file",
            "disk.space": "disk_space",
        }),
        ("shell", "Shell", "dev", "Terminal local protegido pelo classificador de comandos", {
            "run": "run_shell_command",
        }),
        ("gmail", "Gmail", "productivity", "Caixa de entrada e envio de e-mails", {
            "unread.list": "list_unread_emails",
            "send": "send_email",
        }),
        ("calendar", "Google Calendar", "productivity", "Agenda e compromissos", {
            "events.list": "list_upcoming_events",
            "event.create": "create_calendar_event",
        }),
        ("drive", "Google Drive", "productivity", "Busca de arquivos no Drive", {
            "files.search": "search_drive_files",
        }),
        ("browser", "Browser", "web", "Navegador padrão e pesquisas", {
            "open": "open_website",
            "search": "open_browser_search",
        }),
    ]
    for args in groups:
        registry.register(_from_tools(tool_registry, *args))
