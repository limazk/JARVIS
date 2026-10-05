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
import subprocess
from enum import Enum
from typing import Optional

from core.permissions import PermissionDenied, PermissionManager, RiskLevel
from tools.base import Tool, ToolResult


class CommandClass(str, Enum):
    SAFE = "SAFE"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    BLOCKED = "BLOCKED"


_SAFE_PATTERNS = [
    r"^python\s+\S+\.py",
    r"^py\s+\S+\.py",
    r"^git\s+(status|log|diff|branch|remote(\s+-v)?)\b",
    r"^pip\s+list\b",
    r"^pip\s+show\b",
    r"^dir\b",
    r"^ls\b",
    r"^echo\b",
    r"^cd\b",
    r"^node\s+\S+\.js",
    r"^npm\s+(list|-v|--version)\b",
]

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


def classify_command(command: str) -> CommandClass:
    normalized = command.strip().lower()

    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, normalized):
            return CommandClass.BLOCKED

    for pattern in _SAFE_PATTERNS:
        if re.match(pattern, normalized):
            return CommandClass.SAFE

    for pattern in _CONFIRMATION_PATTERNS:
        if re.match(pattern, normalized):
            return CommandClass.CONFIRMATION_REQUIRED

    return CommandClass.CONFIRMATION_REQUIRED


def _run(command: str) -> ToolResult:
    try:
        if os.name == "nt":
            shell_executable = os.environ.get("COMSPEC", "cmd.exe")
        else:
            shell_executable = os.environ.get("SHELL") or "/bin/bash"
        result = subprocess.run(command, shell=True, executable=shell_executable,
                                capture_output=True, text=True, timeout=60)
        output = ((result.stdout or "") + (result.stderr or "")).strip()[:2000]
        success = result.returncode == 0
        message = output if output else ("Comando executado com sucesso." if success else "Comando falhou sem saída.")
        return ToolResult(success=success, message=message, data={"returncode": result.returncode})
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, message=f"O comando '{command}' demorou demais e foi cancelado.")
    except Exception as exc:
        return ToolResult(success=False, message=f"Erro ao executar '{command}': {exc}")


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

        if classification == CommandClass.CONFIRMATION_REQUIRED and permissions is not None:
            try:
                permissions.check("run_shell_command", RiskLevel.MEDIUM, f"Executar no terminal: {command}")
            except PermissionDenied as exc:
                return ToolResult(success=False, message=str(exc))

        return _run(command)

    registry.register(Tool(
        name="run_shell_command",
        description=(
            "Executa um comando de terminal (cmd/PowerShell/bash). Use apenas quando o usuário "
            "pedir explicitamente para rodar um comando, script ou instalar dependências."
        ),
        parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        risk_level=RiskLevel.LOW,  # a checagem real e dinâmica acontece dentro do handler
        handler=handler,
    ))
