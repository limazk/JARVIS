"""
ShellTool — execução controlada de comandos de terminal (seção 27).

NUNCA executa uma string arbitrária "no escuro". Todo comando passa
primeiro por `classify_command`, que devolve um de três níveis:

    SAFE                    -> executa direto
    CONFIRMATION_REQUIRED   -> pede confirmação antes de rodar
    BLOCKED                 -> nunca executa, mesmo com ALLOW_CRITICAL_ACTIONS=true
                                (formatar disco, apagar tudo recursivamente,
                                editar registro crítico, etc. — seção 28)

Comandos não reconhecidos por nenhuma lista caem em
CONFIRMATION_REQUIRED por padrão (postura conservadora).

Nota de arquitetura: diferente das outras tools, o risco aqui
depende do CONTEÚDO do comando, não é um risco fixo por ferramenta.
Por isso o Tool é registrado como LOW_RISK "por fora" (o
PermissionManager genérico deixa passar), mas o handler abaixo faz
sua PRÓPRIA checagem de permissão, dinâmica, usando a mesma
instância de PermissionManager do agente (recebida em register()).
"""
from __future__ import annotations

import re
import os
import shlex
import subprocess
from pathlib import Path
from enum import Enum
from typing import Optional

from core.permissions import PermissionDenied, PermissionManager, RiskLevel
from tools.base import Tool, ToolResult


class CommandClass(str, Enum):
    SAFE = "SAFE"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    BLOCKED = "BLOCKED"


# Apenas leituras inequívocas podem executar sem confirmação.
# Usar fullmatch impede que argumentos posteriores mudem o significado.
_SAFE_PATTERNS = [
    r"git status(?: --short| -sb| --porcelain(?:=v1)?)?",
    r"git log(?: --oneline| -n \d+| -\d+)?",
    r"git diff(?: --stat| --check)?",
    r"git branch(?: --list| -a| -r| --show-current)?",
    r"git remote -v",
    r"pip3? list",
    r"pip3? show [a-z0-9_.-]+",
    r"npm (?:list|-v|--version)",
    r"ls(?: -[lah]+)?",
    r"pwd",
    r"whoami",
    r"echo(?: .*)?",
    r"dir(?: .*)?",
]

# Operadores de shell e substituição de comandos nunca são interpretados.
# Rejeitamos também os operadores entre aspas por prudência.
_SHELL_SYNTAX = re.compile(r"[;&|<>\x60\r\n\x00]|\$[({]|\$\w+")

# Shells explícitos recuperariam interpretação arbitrária de comandos.
_SHELL_EXECUTABLES = frozenset({
    "sh", "bash", "zsh", "fish", "dash", "ksh", "cmd", "cmd.exe",
    "powershell", "powershell.exe", "pwsh", "pwsh.exe", "sudo", "su", "doas",
})


_CONFIRMATION_PATTERNS = [
    r"^pip\s+install\b",
    r"^pip\s+uninstall\b",
    r"^npm\s+install\b",
    r"^git\s+push\b",
    r"^git\s+pull\b",
    r"^git\s+checkout\b",
    r"^git\s+reset\b",
    r"^git\s+clean\b",
    r"^move\b",
    r"^mv\b",
    r"^copy\b",
    r"^cp\b",
    r"^ren(ame)?\b",
    r"^taskkill\b",
    r"^kill\b",
    r"^mkdir\b",
    r"^new-item\b",
]

# Qualquer coisa que possa inutilizar o Windows ou apagar dados em massa.
_BLOCKED_PATTERNS = [
    r"^format\b",
    r"diskpart",
    r"^rm\s+-rf\s+/",
    r"^rm\s+-rf\s+\*",
    r"del\s+/s\s+/q\b",
    r"rd\s+/s\s+/q\b",
    r"^shutdown\b",
    r"^restart-computer\b",
    r"reg\s+delete\b",
    r"bcdedit",
    r"cipher\s+/w",
    r":\(\)\s*\{\s*:\|:&\s*\};:",  # fork bomb
]


def _argv(command: str) -> list[str]:
    """Interpreta apenas aspas/argumentos, NUNCA operadores de shell."""
    try:
        arguments = shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        return []
    if os.name == "nt":
        # shlex em modo Windows preserva aspas delimitadoras.
        arguments = [
            arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1] == '"' else arg
            for arg in arguments
        ]
    return arguments


def classify_command(command: str) -> CommandClass:
    if not isinstance(command, str) or not command.strip() or len(command) > 4096:
        return CommandClass.BLOCKED
    if _SHELL_SYNTAX.search(command):
        return CommandClass.BLOCKED

    normalized = command.strip().lower()
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, normalized):
            return CommandClass.BLOCKED

    argv = _argv(command)
    if not argv:
        return CommandClass.BLOCKED
    executable = Path(argv[0].replace("\\", "/")).name.lower()
    if executable in _SHELL_EXECUTABLES:
        return CommandClass.BLOCKED

    if argv[0].lower() == executable and any(
        re.fullmatch(pattern, normalized) for pattern in _SAFE_PATTERNS
    ):
        return CommandClass.SAFE

    return CommandClass.CONFIRMATION_REQUIRED


def _run(command: str) -> ToolResult:
    """Roda executável com argv e shell=False; nunca interpreta scripts de shell."""
    if classify_command(command) == CommandClass.BLOCKED:
        return ToolResult(success=False, message="Comando bloqueado pela política de segurança.")

    argv = _argv(command)
    if not argv:
        return ToolResult(success=False, message="Comando vazio ou aspas inválidas.")
    executable = argv[0].lower()

    # Built-ins de cmd.exe não são executáveis independentes.
    if executable == "echo":
        return ToolResult(success=True, message=" ".join(argv[1:]))
    if executable == "dir":
        try:
            path = Path(argv[1]).expanduser() if len(argv) == 2 else Path.cwd()
            if len(argv) > 2:
                return ToolResult(success=False, message="Use 'dir' com no máximo um caminho.")
            return ToolResult(success=True, message="\n".join(
                sorted(item.name for item in path.iterdir())[:100]
            ) or "(pasta vazia)")
        except OSError as exc:
            return ToolResult(success=False, message=f"Não consegui listar a pasta: {exc}")
    if executable == "cd":
        return ToolResult(
            success=False,
            message="O terminal do JARVIS não mantém diretório entre comandos. Use caminhos absolutos.",
        )

    try:
        result = subprocess.run(
            argv, shell=False, capture_output=True, text=True, timeout=60
        )
        output = ((result.stdout or "") + (result.stderr or "")).strip()[:2000]
        success = result.returncode == 0
        message = output if output else (
            "Comando executado com sucesso." if success else "Comando falhou sem saída."
        )
        return ToolResult(success=success, message=message, data={"returncode": result.returncode})
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, message="O comando excedeu 60 segundos e foi interrompido.")
    except (OSError, ValueError) as exc:
        return ToolResult(success=False, message=f"Não foi possível iniciar o executável: {exc}")


def register(registry, permissions: Optional[PermissionManager] = None) -> None:
    def handler(command: str, **_: object) -> ToolResult:
        classification = classify_command(command)

        if classification == CommandClass.BLOCKED:
            return ToolResult(
                success=False,
                message=(
                    f"O comando '{command}' foi bloqueado por segurança — ele pode causar dano "
                    "irreversível ao sistema e não pode ser executado pelo Jarvis."
                ),
            )

        if classification == CommandClass.CONFIRMATION_REQUIRED:
            if permissions is None:
                return ToolResult(
                    success=False,
                    message="Esse comando precisa de confirmação, mas não há um autorizador configurado.",
                )
            try:
                permissions.check("run_shell_command", RiskLevel.MEDIUM, f"Executar no terminal: {command}")
            except PermissionDenied as exc:
                return ToolResult(success=False, message=str(exc))

        return _run(command)

    registry.register(Tool(
        name="run_shell_command",
        description=(
            "Executa um programa de terminal sem shell. Use apenas quando o usuário "
            "pedir explicitamente; comandos não triviais exigem confirmação."
        ),
        parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        risk_level=RiskLevel.LOW,  # a checagem real e dinâmica acontece dentro do handler
        handler=handler,
    ))
