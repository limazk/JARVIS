"""
Lembretes — seção 21 do spec.

`parse_reminder_text` separa "daqui a quanto tempo" do "o quê" numa
frase em português livre (ex.: "em 10 minutos de estudar" ->
daqui a 10 min, texto "estudar"). Não é um NLP sofisticado — é um
conjunto de regras que cobre os casos do spec (seção 47): "em N
minutos/horas", "às HH[:MM]", "amanhã [às HH[:MM]]".

O ReminderScheduler roda em uma thread separada (daemon) e verifica
periodicamente se algum lembrete venceu, disparando notificação
nativa do Windows + callback de voz (quando a ETAPA 5 estiver
pronta). Isso cumpre a seção 21: "o sistema deve verificar
lembretes enquanto estiver rodando".
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from core.permissions import RiskLevel
from memory.database import get_connection, log_activity
from tools._notify import notify, play_alert_sound
from tools.base import Tool, ToolResult

logger = logging.getLogger("jarvis.reminders")


def parse_reminder_text(raw_text: str) -> tuple[Optional[datetime], str]:
    """Devolve (quando, texto_do_lembrete). `quando` é None se não conseguir entender."""
    text = raw_text.strip().lower()
    now = datetime.now()

    # "em/daqui a N minutos/horas [de] <texto>"
    m = re.match(r"^(em|daqui a)\s+(?P<n>\d+)\s*(?P<unit>minuto|minutos|min|hora|horas|h)\s*(de\s+)?(?P<rest>.*)$", text)
    if m:
        n = int(m.group("n"))
        unit = m.group("unit")
        delta = timedelta(hours=n) if unit.startswith("h") else timedelta(minutes=n)
        return now + delta, m.group("rest").strip() or "lembrete"

    # "amanhã às HH[:MM] [de] <texto>"
    m = re.match(r"^amanh[ãa]\s+[àa]s?\s*(?P<h>\d{1,2})(:(?P<min>\d{2}))?\s*(de\s+)?(?P<rest>.*)$", text)
    if m:
        hour, minute = int(m.group("h")), int(m.group("min") or 0)
        when = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return when, m.group("rest").strip() or "lembrete"

    # "amanhã de <texto>" (sem horário -> 09:00)
    m = re.match(r"^amanh[ãa]\s+(de\s+)?(?P<rest>.*)$", text)
    if m:
        when = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return when, m.group("rest").strip() or "lembrete"

    # "às HH[:MM] [de] <texto>"
    m = re.match(r"^[àa]s?\s*(?P<h>\d{1,2})(:(?P<min>\d{2}))?\s*(de\s+)?(?P<rest>.*)$", text)
    if m:
        hour, minute = int(m.group("h")), int(m.group("min") or 0)
        when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if when <= now:
            when += timedelta(days=1)
        return when, m.group("rest").strip() or "lembrete"

    return None, text


def add_reminder(raw_text: str, **_: object) -> ToolResult:
    when, text = parse_reminder_text(raw_text)
    if when is None:
        return ToolResult(
            success=False,
            message=(
                f"Não entendi quando devo te lembrar de '{raw_text}'. "
                "Tente algo como 'em 10 minutos de estudar' ou 'às 18h de pagar a conta'."
            ),
        )
    with get_connection() as conn:
        conn.execute("INSERT INTO reminders (text, due_at) VALUES (?, ?)", (text, when.isoformat()))
    return ToolResult(
        success=True,
        message=f"Lembrete criado: vou te lembrar de '{text}' em {when.strftime('%d/%m às %H:%M')}.",
        data={"due_at": when.isoformat(), "text": text},
    )


def list_reminders(**_: object) -> ToolResult:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT text, due_at FROM reminders WHERE status = 'pending' ORDER BY due_at ASC"
        ).fetchall()
    if not rows:
        return ToolResult(success=True, message="Você não tem lembretes pendentes.")
    listed = "\n".join(f"- {r['text']} ({datetime.fromisoformat(r['due_at']).strftime('%d/%m %H:%M')})" for r in rows)
    return ToolResult(success=True, message=f"Seus lembretes:\n{listed}")


def register(registry) -> None:
    registry.register(Tool(
        name="add_reminder",
        description=(
            "Cria um lembrete. Passe o texto completo do pedido do usuário sem a palavra 'lembra' "
            "(ex.: 'em 10 minutos de estudar', 'às 18h de pagar a conta', 'amanhã de comprar pão')."
        ),
        parameters={"type": "object", "properties": {"raw_text": {"type": "string"}}, "required": ["raw_text"]},
        risk_level=RiskLevel.LOW,
        handler=add_reminder,
        confirmation_template="Lembrete: {raw_text}",
    ))
    registry.register(Tool(
        name="list_reminders",
        description="Lista os lembretes pendentes.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=list_reminders,
    ))


class ReminderScheduler:
    """Verifica periodicamente se algum lembrete venceu (seção 21)."""

    def __init__(self, on_due: Optional[Callable[[str], None]] = None, interval_seconds: int = 15) -> None:
        self.on_due = on_due
        self.interval_seconds = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-reminder-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=max(1.0, min(float(self.interval_seconds), 5.0)))
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_due()
            except Exception:
                logger.exception("Erro ao checar lembretes.")
            self._stop_event.wait(self.interval_seconds)

    def _check_due(self) -> None:
        now_iso = datetime.now().isoformat()
        with get_connection() as conn:
            due_rows = conn.execute(
                "SELECT id, text FROM reminders WHERE status = 'pending' AND due_at <= ?", (now_iso,)
            ).fetchall()
            for row in due_rows:
                conn.execute("UPDATE reminders SET status = 'done' WHERE id = ?", (row["id"],))

        for row in due_rows:
            message = f"Você pediu para eu lembrar de {row['text']}."
            notify("Jarvis — Lembrete", message)
            play_alert_sound()
            log_activity(f"Lembrete disparado: {row['text']}")
            if self.on_due:
                self.on_due(message)
