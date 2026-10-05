from __future__ import annotations

import logging

import pytest

from config.settings import settings
from core.brain import LLMProvider
from core.context import ConversationContext
from core.intent import match_local_intent
from core.performance import request_trace
from core.permissions import PermissionManager, RiskLevel
from core.router import Router
from integrations.rotina import RotinaClient
from tools.base import Tool, ToolResult
from tools.registry import ToolRegistry


@pytest.mark.parametrize(("phrase", "tool"), [
    ("O que tenho para fazer?", "get_today_tasks"),
    ("Minhas tarefas de hoje", "get_today_tasks"),
    ("Qual é minha rotina hoje?", "get_rotina_summary"),
    ("Qual minha próxima atividade?", "get_rotina_summary"),
    ("Quanto eu gastei?", "get_financial_summary"),
    ("Como estão minhas finanças?", "get_financial_summary"),
    ("Quanto meu negócio fez?", "get_business_summary"),
    ("Quanto faturei?", "get_business_summary"),
    ("Quais são meus lembretes?", "list_reminders"),
    ("Minha agenda hoje", "list_upcoming_events"),
    ("Status do sistema", "system_status"),
    ("Abra o Firefox", "open_application"),
    ("Volume 35", "set_volume"),
    ("Trava a tela", "lock_computer"),
])
def test_priority_phrases_use_deterministic_router(phrase, tool):
    match = match_local_intent(phrase)
    assert match.matched and match.tool_name == tool


class NeverLLM(LLMProvider):
    available = True

    def decide(self, system_prompt, messages, tools):
        raise AssertionError("o LLM não deve ser chamado no fast path")


def test_fast_read_executes_registry_and_skips_llm(monkeypatch):
    monkeypatch.setattr(settings, "user_title", "Senhor")
    registry = ToolRegistry()
    registry.register(Tool("get_today_tasks", "tarefas", {"type": "object", "properties": {}},
                           RiskLevel.LOW, lambda: ToolResult(True, "Você tem duas tarefas hoje.")))
    router = Router(NeverLLM(), registry, ConversationContext(), PermissionManager())
    result = router.handle("Quais são minhas tarefas?", response_mode="voice")
    assert result.tool_used == "get_today_tasks"
    assert result.reply.startswith("Senhor,")


class CountingSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        payload = [{"id": "1", "title": "Teste", "date": "2099-01-01"}]
        return type("Response", (), {
            "status_code": 200, "ok": True, "content": b"x", "json": lambda self: payload,
        })()


def test_rotina_cache_reuses_read_and_write_invalidates(monkeypatch):
    monkeypatch.setattr(settings, "fast_cache_enabled", True)
    monkeypatch.setattr(settings, "fast_cache_ttl", 15)
    client = RotinaClient()
    session = CountingSession()
    client._session = session
    client.tasks()
    client.tasks()
    assert len(session.calls) == 1
    client.add_task("Nova")
    client.tasks()
    assert len(session.calls) == 3  # POST e nova leitura depois da invalidação


def test_performance_log_contains_only_ids_and_timings(caplog):
    secret = "salario-super-secreto"
    with caplog.at_level(logging.INFO, logger="jarvis.performance"):
        with request_trace() as trace:
            trace.set("routing_duration", 0.001)
            trace.log()
    output = caplog.text
    assert "PERF request=" in output
    assert "routing_duration=" in output
    assert secret not in output
