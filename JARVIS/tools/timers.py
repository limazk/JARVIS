"""
Timer/cronômetro — seção 22 do spec.

Diferente dos lembretes, timers são efêmeros (não persistem no
banco — se o Jarvis for reiniciado, o timer se perde, o que é
aceitável para este caso de uso). Implementado com
`threading.Timer`, que dispara a notificação em uma thread separada
sem bloquear o resto do programa.
"""
from __future__ import annotations

import re
import threading
from typing import Callable, Optional

from core.permissions import RiskLevel
from memory.database import log_activity
from tools._notify import notify, play_alert_sound
from tools.base import Tool, ToolResult

_active_timers: dict[str, threading.Timer] = {}
_on_done_callback: Optional[Callable[[str], None]] = None


def set_on_done_callback(callback: Callable[[str], None]) -> None:
    """Permite à interface (ETAPA 6) ou à voz (ETAPA 5) reagir ao fim do timer."""
    global _on_done_callback
    _on_done_callback = callback


def _parse_duration_seconds(raw_duration: str) -> Optional[int]:
    text = raw_duration.strip().lower()
    m = re.search(r"(?P<n>\d+)\s*(?P<unit>segundo|segundos|seg|minuto|minutos|min|hora|horas|h)", text)
    if not m:
        return None
    n = int(m.group("n"))
    unit = m.group("unit")
    if unit.startswith("h"):
        return n * 3600
    if unit in {"segundo", "segundos", "seg"}:
        return n
    return n * 60  # "minuto"/"minutos"/"min" (e qualquer outro caso cai aqui, por segurança)


def start_timer(raw_duration: str, **_: object) -> ToolResult:
    seconds = _parse_duration_seconds(raw_duration)
    if seconds is None or seconds <= 0:
        return ToolResult(
            success=False,
            message=f"Não entendi a duração '{raw_duration}'. Tente algo como '5 minutos' ou '30 segundos'.",
        )

    label = raw_duration.strip()

    def _fire() -> None:
        message = f"Timer de {label} terminou."
        notify("Jarvis — Timer", message)
        play_alert_sound()
        log_activity(f"Timer concluído: {label}")
        _active_timers.pop(label, None)
        if _on_done_callback:
            _on_done_callback(message)

    timer = threading.Timer(seconds, _fire)
    timer.daemon = True
    _active_timers[label] = timer
    timer.start()

    return ToolResult(success=True, message=f"Timer de {label} iniciado.", data={"seconds": seconds})


def register(registry) -> None:
    registry.register(Tool(
        name="start_timer",
        description="Inicia um cronômetro/timer que avisa quando o tempo termina (ex.: '5 minutos', '30 segundos').",
        parameters={"type": "object", "properties": {"raw_duration": {"type": "string"}}, "required": ["raw_duration"]},
        risk_level=RiskLevel.LOW,
        handler=start_timer,
        confirmation_template="Timer: {raw_duration}",
    ))
