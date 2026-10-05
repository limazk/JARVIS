"""
Testes do briefing matinal (tools/briefing.py) — orquestra ferramentas
que já existem (clima, Gmail, Calendar, lembretes) mais um recap da
memória de longo prazo, tudo local, sem LLM.
"""
from __future__ import annotations

from config.settings import settings
from memory.memory import remember_fact
from tools.base import ToolResult
from tools.briefing import morning_briefing
from tools.reminders import add_reminder


def test_sem_nenhum_dado_real_avisa_honestamente(monkeypatch):
    # Clima, Gmail, Calendar e até a consulta de lembretes falhando (ex.:
    # banco indisponível) -> nada pra mostrar de verdade, e o Jarvis tem
    # que dizer isso claramente, nunca inventar uma seção vazia. (Note:
    # "você não tem lembretes pendentes" É um dado real e por isso conta
    # como seção válida — por isso aqui simulamos até essa consulta
    # falhando, não só "sem lembretes".)
    monkeypatch.setattr(
        "tools.weather.get_weather", lambda *a, **k: ToolResult(success=False, message="sem internet")
    )
    monkeypatch.setattr(
        "tools.gcalendar.list_upcoming_events",
        lambda *a, **k: ToolResult(success=False, message="Google não configurado"),
    )
    monkeypatch.setattr(
        "tools.gmail.list_unread_emails",
        lambda *a, **k: ToolResult(success=False, message="Google não configurado"),
    )
    monkeypatch.setattr(
        "tools.reminders.list_reminders",
        lambda *a, **k: ToolResult(success=False, message="banco indisponível"),
    )

    result = morning_briefing()

    assert result.success is True
    assert "bom dia" in result.message.lower()
    assert "não tenho nenhuma atualização" in result.message.lower()
    assert result.data["secoes"] == 0


def test_inclui_clima_agenda_email_e_lembretes_quando_disponiveis(monkeypatch):
    monkeypatch.setattr(
        "tools.weather.get_weather", lambda *a, **k: ToolResult(success=True, message="Agora em Brasília: ensolarado, 28°C.")
    )
    monkeypatch.setattr(
        "tools.gcalendar.list_upcoming_events",
        lambda *a, **k: ToolResult(success=True, message="Seus compromissos:\n- 10:00: Reunião com fornecedor"),
    )
    monkeypatch.setattr(
        "tools.gmail.list_unread_emails",
        lambda *a, **k: ToolResult(success=True, message="E-mails não lidos:\n- banco@exemplo.com: Fatura"),
    )
    add_reminder("em 30 minutos de ligar pro cliente")

    result = morning_briefing()

    assert result.success is True
    assert "ensolarado" in result.message
    assert "Reunião com fornecedor" in result.message
    assert "Fatura" in result.message
    assert "ligar pro cliente" in result.message
    assert result.data["secoes"] == 4


def test_recapitulacao_inclui_fatos_guardados_nas_ultimas_24h(monkeypatch):
    monkeypatch.setattr(
        "tools.weather.get_weather", lambda *a, **k: ToolResult(success=False, message="sem internet")
    )
    monkeypatch.setattr(
        "tools.gcalendar.list_upcoming_events", lambda *a, **k: ToolResult(success=False, message="x")
    )
    monkeypatch.setattr(
        "tools.gmail.list_unread_emails", lambda *a, **k: ToolResult(success=False, message="x")
    )
    remember_fact("prefiro reuniões à tarde")

    result = morning_briefing()

    assert "Desde ontem, guardei" in result.message
    assert "prefiro reuniões à tarde" in result.message


def test_uma_secao_falhando_nunca_derruba_o_briefing_inteiro(monkeypatch):
    def _explode(*a, **k):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("tools.weather.get_weather", _explode)
    monkeypatch.setattr(
        "tools.gcalendar.list_upcoming_events",
        lambda *a, **k: ToolResult(success=True, message="Seus compromissos:\n- 09:00: Dentista"),
    )
    monkeypatch.setattr("tools.gmail.list_unread_emails", lambda *a, **k: ToolResult(success=False, message="x"))

    result = morning_briefing()

    assert result.success is True
    assert "Dentista" in result.message


def test_saudacao_usa_user_title_quando_configurado(monkeypatch):
    monkeypatch.setattr(settings, "user_title", "Senhor")
    monkeypatch.setattr("tools.weather.get_weather", lambda *a, **k: ToolResult(success=False, message="x"))
    monkeypatch.setattr("tools.gcalendar.list_upcoming_events", lambda *a, **k: ToolResult(success=False, message="x"))
    monkeypatch.setattr("tools.gmail.list_unread_emails", lambda *a, **k: ToolResult(success=False, message="x"))

    result = morning_briefing()

    assert "Bom dia, Senhor." in result.message


def test_registrado_no_registry_com_risco_baixo():
    from core.permissions import RiskLevel
    from tools.registry import ToolRegistry
    from tools.briefing import register

    registry = ToolRegistry()
    register(registry)

    tool = registry.get("morning_briefing")
    assert tool is not None
    assert tool.risk_level == RiskLevel.LOW
