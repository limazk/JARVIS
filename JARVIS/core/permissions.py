"""
PermissionManager — a porta de segurança do Jarvis (seção 28 do spec).

Toda ferramenta declara um `risk_level`. Antes de qualquer execução,
o router passa pela checagem daqui. É isso que impede o agente de
fazer algo destrutivo sozinho.

Níveis:
    LOW      -> executa imediatamente
    MEDIUM   -> mostra o que fará e pede confirmação
    HIGH     -> exige confirmação explícita, mostrando detalhes
    CRITICAL -> bloqueado por padrão (só roda com ALLOW_CRITICAL_ACTIONS=true)
"""
from __future__ import annotations

from enum import Enum
from typing import Callable, Optional

from config.settings import settings


class RiskLevel(str, Enum):
    LOW = "LOW_RISK"
    MEDIUM = "MEDIUM_RISK"
    HIGH = "HIGH_RISK"
    CRITICAL = "CRITICAL"


# Callback de confirmação: recebe uma mensagem explicando a ação e
# devolve True/False. O modo texto usa input() no console; a
# interface gráfica (ETAPA 6) vai passar uma caixa de diálogo.
ConfirmCallback = Callable[[str], bool]


class PermissionDenied(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.reason


class PermissionManager:
    """Decide se uma ação pode rodar, e como pedir confirmação quando necessário."""

    def __init__(self, confirm_callback: Optional[ConfirmCallback] = None) -> None:
        self.confirm_callback = confirm_callback or self._console_confirm

    @staticmethod
    def _console_confirm(message: str) -> bool:
        answer = input(f"\n[Jarvis] {message}\nConfirma? (sim/não): ").strip().lower()
        return answer in {"s", "sim", "y", "yes"}

    def check(self, tool_name: str, risk_level: RiskLevel, description: str) -> bool:
        """
        Retorna True se a ação pode ser executada.
        Lança PermissionDenied se o usuário recusar, ou se for CRITICAL bloqueado.
        """
        if risk_level == RiskLevel.LOW:
            return True

        if risk_level == RiskLevel.CRITICAL and not settings.allow_critical_actions:
            raise PermissionDenied(
                f"'{tool_name}' é uma ação CRÍTICA e está bloqueada por padrão. "
                "Ative ALLOW_CRITICAL_ACTIONS=true no .env por sua conta e risco."
            )

        prefix = "Ação de risco alto" if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "Confirmação necessária"
        approved = self.confirm_callback(f"{prefix}: {description}")
        if not approved:
            raise PermissionDenied(f"Ação '{tool_name}' cancelada pelo usuário.")
        return True
