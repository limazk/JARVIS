"""
Google Calendar — ver e criar compromissos direto do Jarvis. Parte da
integração Google (item do roadmap "Gmail/Calendar/Drive"); mesma
autenticação/configuração do Gmail (tools/google_auth.py) — um único
login cobre Gmail + Calendar + Drive.

Nome do arquivo é `gcalendar.py` (não `calendar.py`) de propósito, pra
não colidir com o módulo `calendar` da biblioteca padrão do Python.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult
from tools.google_auth import get_google_service, no_google_credentials_result


def list_upcoming_events(days: int = 1, **_: object) -> ToolResult:
    service = get_google_service("calendar", "v3")
    if service is None:
        return no_google_credentials_result()
    try:
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=max(1, days))).isoformat() + "Z"
        resp = (
            service.events()
            .list(
                calendarId="primary", timeMin=time_min, timeMax=time_max,
                singleEvents=True, orderBy="startTime", maxResults=20,
            )
            .execute()
        )
        events = resp.get("items", [])
        if not events:
            return ToolResult(success=True, message="Nenhum compromisso nesse período.")
        lines = []
        for e in events:
            start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "?"))
            lines.append(f"- {start}: {e.get('summary', '(sem título)')}")
        return ToolResult(success=True, message="Seus compromissos:\n" + "\n".join(lines))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui consultar a agenda: {exc}")


def create_event(title: str, start_iso: str, duration_minutes: int = 60, **_: object) -> ToolResult:
    service = get_google_service("calendar", "v3")
    if service is None:
        return no_google_credentials_result()
    try:
        start_dt = datetime.fromisoformat(start_iso)
    except ValueError:
        return ToolResult(
            success=False,
            message=f"Não entendi a data/hora '{start_iso}' (use o formato AAAA-MM-DDTHH:MM:SS).",
        )
    end_dt = start_dt + timedelta(minutes=max(1, duration_minutes))
    try:
        event = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }
        service.events().insert(calendarId="primary", body=event).execute()
        return ToolResult(success=True, message=f"Compromisso '{title}' criado para {start_dt.strftime('%d/%m às %H:%M')}.")
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui criar o compromisso: {exc}")


def register(registry) -> None:
    registry.register(Tool(
        name="list_upcoming_events",
        description="Lista os compromissos do Google Calendar nos próximos N dias (padrão 1 = hoje).",
        parameters={
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "Quantos dias à frente, padrão 1"}},
        },
        risk_level=RiskLevel.LOW,
        handler=list_upcoming_events,
    ))
    registry.register(Tool(
        name="create_calendar_event",
        description=(
            "Cria um compromisso no Google Calendar. 'start_iso' no formato "
            "AAAA-MM-DDTHH:MM:SS — use a data/hora atual (informada no início desta conversa) "
            "como referência pra calcular pedidos relativos tipo 'amanhã às 15h'. Exige confirmação."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_iso": {"type": "string", "description": "AAAA-MM-DDTHH:MM:SS"},
                "duration_minutes": {"type": "integer", "description": "Padrão 60"},
            },
            "required": ["title", "start_iso"],
        },
        risk_level=RiskLevel.MEDIUM,
        handler=create_event,
        confirmation_template="Criar compromisso '{title}' em {start_iso}",
    ))
