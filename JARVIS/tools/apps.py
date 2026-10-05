"""
Ferramenta: abrir programas no Windows — seção 12 do spec.

Ordem de resolução do nome de um app:
    1) config/apps.json (caminho customizado pelo usuário)
    2) Apelidos comuns (chrome, edge, discord, spotify, ...) que o
       próprio Windows sabe resolver sem caminho completo
    3) Busca do executável no PATH (shutil.which)
Se nada funcionar, devolve um erro claro em vez de fingir sucesso.
"""
from __future__ import annotations

import json
import platform
import re
import shutil
from pathlib import Path

from config.settings import settings
from core.permissions import RiskLevel
from tools.base import Tool, ToolResult
from platform_services import get_platform_services

# Comandos que o Windows já resolve sozinho (via "start" / os.startfile).
_KNOWN_ALIASES: dict[str, str] = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "discord": "discord",
    "spotify": "spotify",
    "steam": "steam",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "explorador de arquivos": "explorer",
    "explorer": "explorer",
    "calculadora": "calc",
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "cmd": "cmd",
    "prompt de comando": "cmd",
    "powershell": "powershell",
    "navegador": "msedge",
}

_LINUX_ALIASES: dict[str, str] = {
    "chrome": "google-chrome", "google chrome": "google-chrome",
    "firefox": "firefox", "navegador": "firefox", "discord": "discord",
    "spotify": "spotify", "steam": "steam", "vscode": "code", "vs code": "code",
    "visual studio code": "code", "explorador de arquivos": "xdg-open .",
    "terminal": "x-terminal-emulator", "bash": "/bin/bash",
}


def _load_custom_apps() -> dict[str, str | list[str]]:
    path: Path = settings.apps_json_path
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        system_key = "windows" if platform.system() == "Windows" else "linux"
        apps: dict[str, str | list[str]] = {}
        for key, value in data.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict):
                selected = value.get(system_key)
                if isinstance(selected, (str, list)):
                    apps[key] = selected
            elif isinstance(value, (str, list)):  # schema legado continua válido
                apps[key] = value
        return apps
    except (json.JSONDecodeError, OSError):
        return {}


def open_application(app_name: str, **_: object) -> ToolResult:
    key = app_name.strip().lower()
    custom_apps = _load_custom_apps()

    if key in custom_apps:
        return _launch(custom_apps[key], app_name)

    aliases = _KNOWN_ALIASES if platform.system() == "Windows" else _LINUX_ALIASES
    if key in aliases:
        target = aliases[key]
        executable = target.split()[0]
        if not Path(executable).is_absolute() and not shutil.which(executable):
            return ToolResult(False, f"O aplicativo '{app_name}' não está instalado ou não foi encontrado no PATH.")
        return _launch(target, app_name)

    found = shutil.which(key)
    if found:
        return _launch(found, app_name)

    # Não é um programa instalado -> tenta como site conhecido (youtube, github, ...)
    from tools.browser import open_website

    if key in _website_aliases():
        return open_website(app_name)

    # "abre meu github", "abre minha calculadora"... -> tira o possessivo e tenta
    # resolver a palavra que sobrou como programa/site conhecido, antes de cair
    # na memória de longo prazo (que é só pra apelidos pessoais de verdade, tipo
    # "meu editor").
    bare = _strip_possessive(key)
    if bare is not None and bare != key:
        if bare in custom_apps or bare in aliases or bare in _website_aliases():
            return open_application(bare)

    # Última tentativa: "meu editor", "meu navegador"... -> consulta a memória de
    # longo prazo (seção 29 do spec: "lembra que meu editor é o VS Code" depois
    # "abre meu editor" deve entender VS Code).
    resolved = _resolve_via_memory(key, custom_apps)
    if resolved is not None:
        return open_application(resolved)

    return ToolResult(
        success=False,
        message=(
            f"Não encontrei o programa '{app_name}'. Adicione o caminho completo dele em "
            f"config/apps.json, ou me diga 'lembra que {app_name} é <nome do programa>'."
        ),
    )


_POSSESSIVE_PREFIXES = ("meu ", "minha ", "meus ", "minhas ")


def _strip_possessive(key: str) -> str | None:
    """'meu github' -> 'github'; devolve None se não começar com possessivo."""
    for prefix in _POSSESSIVE_PREFIXES:
        if key.startswith(prefix):
            return key[len(prefix):].strip()
    return None


def _resolve_via_memory(key: str, custom_apps: dict[str, str | list[str]]) -> str | None:
    from memory.memory import recall_relevant

    known_names = set(_KNOWN_ALIASES.keys()) | set(_LINUX_ALIASES.keys()) | set(custom_apps.keys()) | _website_aliases()
    for fact in recall_relevant(key):
        fact_lower = fact.lower()
        for name in known_names:
            if name in fact_lower:
                return name
    return None


def _website_aliases() -> set:
    from tools.browser import KNOWN_WEBSITES

    return set(KNOWN_WEBSITES.keys())


_VERSION_FOLDER = re.compile(r"^app-[\d.]+$")


def _version_key(folder_name: str) -> tuple:
    parts = folder_name[len("app-"):].split(".")
    return tuple(int(p) if p.isdigit() else 0 for p in parts)


def _resolve_versioned_path(path_str: str) -> str:
    """
    Alguns apps (Discord, e outros baseados no mesmo instalador Squirrel)
    ficam numa subpasta com o número da versão (ex.: app-1.0.9257), que
    muda sozinho a cada atualização automática — um caminho fixo no
    config/apps.json quebra no próximo update do programa. Se o caminho
    configurado não existir mais, mas o padrão "app-<versão>" for
    reconhecível, procura a pasta de versão mais recente no mesmo lugar
    antes de desistir.
    """
    path = Path(path_str)
    if path.exists():
        return path_str

    if not _VERSION_FOLDER.match(path.parent.name):
        return path_str

    apps_root = path.parent.parent
    if not apps_root.is_dir():
        return path_str

    candidates = [d for d in apps_root.iterdir() if d.is_dir() and _VERSION_FOLDER.match(d.name)]
    if not candidates:
        return path_str

    newest = max(candidates, key=lambda d: _version_key(d.name))
    newer_path = newest / path.name
    return str(newer_path) if newer_path.exists() else path_str


def _launch(target: str | list[str], app_name: str) -> ToolResult:
    resolved: str | list[str] = _resolve_versioned_path(target) if isinstance(target, str) and platform.system() == "Windows" else target
    result = get_platform_services().open_application(resolved, app_name)
    return ToolResult(result.success, result.message, result.data)


def register(registry) -> None:
    registry.register(
        Tool(
            name="open_application",
            description="Abre um programa/aplicativo no sistema pelo nome (ex.: firefox, chrome, spotify, discord ou vscode).",
            parameters={
                "type": "object",
                "properties": {"app_name": {"type": "string", "description": "Nome do programa a abrir"}},
                "required": ["app_name"],
            },
            risk_level=RiskLevel.LOW,
            handler=open_application,
            confirmation_template="Abrir {app_name}",
        )
    )
