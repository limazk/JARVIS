"""Tools do ROTINA. Nenhuma delas lê ou grava data.json diretamente."""
from __future__ import annotations

import time
from typing import Any, Callable

from core.permissions import RiskLevel
from jarvis_rotina import RotinaClient, RotinaError
from personality.engine import PersonalityEngine
from tools.base import Tool, ToolResult


_SHARED_CLIENT = RotinaClient()


def _client() -> RotinaClient:
    return _SHARED_CLIENT


def _direct(text: str) -> str:
    return PersonalityEngine().apply_direct(text, response_mode="voice")


def _result(call: Callable[[], Any], message: Callable[[Any], str]) -> ToolResult:
    try:
        data = call()
        return ToolResult(True, _direct(message(data)), {"result": data})
    except (RotinaError, ValueError) as exc:
        return ToolResult(False, str(exc))


def get_rotina_summary(**_: object) -> ToolResult:
    return _result(_client().summary, lambda d: (
        f"Hoje há {d.get('rotina', {}).get('tarefas_hoje', 0)} tarefas, "
        f"com {d.get('rotina', {}).get('concluidas', 0)} concluídas."
    ))


def get_today_tasks(**_: object) -> ToolResult:
    def message(tasks: list[dict]) -> str:
        if not tasks:
            return "você não tem tarefas registradas para hoje."
        today = time.strftime("%Y-%m-%d")
        completed = sum(today in (task.get("doneDates") or []) for task in tasks)
        pending = len(tasks) - completed
        names = "; ".join(str(t.get("title", "sem título")) for t in tasks if today not in (t.get("doneDates") or []))
        summary = f"você tem {len(tasks)} tarefas hoje: {completed} concluídas e {pending} pendentes."
        return f"{summary} Pendentes: {names}." if names else summary
    return _result(_client().today_tasks, message)


def add_task(title: str, **kwargs: object) -> ToolResult:
    return _result(lambda: _client().add_task(title, date=kwargs.get("date") or None),
                   lambda _: f"Tarefa '{title.strip()}' adicionada.")


def complete_task(title_or_id: str, **_: object) -> ToolResult:
    return _result(lambda: _client().complete_task(title_or_id),
                   lambda task: f"Tarefa '{task.get('title', title_or_id)}' concluída.")


def add_income(amount: float, description: str = "Entrada", **_: object) -> ToolResult:
    return _result(lambda: _client().add_transaction("in", amount, description),
                   lambda _: f"Entrada de R$ {float(amount):.2f} registrada.")


def add_expense(amount: float, description: str = "Despesa", **_: object) -> ToolResult:
    return _result(lambda: _client().add_transaction("out", amount, description),
                   lambda _: f"Despesa de R$ {float(amount):.2f} registrada.")


def get_financial_summary(**_: object) -> ToolResult:
    return _result(_client().weekly_summary, lambda d: (
        f"Nesta semana: R$ {d['personal_finance']['income']:.2f} em entradas pessoais, "
        f"R$ {d['personal_finance']['expenses']:.2f} em gastos e saldo de R$ {d['personal_finance']['net']:.2f}."
    ))


def get_business_summary(**_: object) -> ToolResult:
    return _result(_client().weekly_summary, lambda d: (
        f"Nos negócios: R$ {d['business']['revenue']:.2f} de receita, "
        f"R$ {d['business']['cost']:.2f} de custos e R$ {d['business']['profit']:.2f} de lucro registrado."
    ))


def get_weekly_finance(**_: object) -> ToolResult:
    return _result(_client().weekly_summary, lambda d: (
        f"Entradas pessoais: R$ {d['personal_finance']['income']:.2f}; gastos: "
        f"R$ {d['personal_finance']['expenses']:.2f}; saldo: R$ {d['personal_finance']['net']:.2f}. "
        f"Negócios, separadamente: receita R$ {d['business']['revenue']:.2f}, custos "
        f"R$ {d['business']['cost']:.2f}, lucro R$ {d['business']['profit']:.2f}."
    ))


def get_weekly_productivity(**_: object) -> ToolResult:
    return _result(_client().weekly_summary, lambda d: (
        f"Nesta semana: {d['productivity']['tasks']} tarefas, {d['productivity']['completed']} concluídas, "
        f"{d['productivity']['pending']} pendentes ({d['productivity']['completion_pct']:.0f}%)."
    ))


def compare_weekly_finance(**_: object) -> ToolResult:
    def message(data: dict) -> str:
        current = data["personal_finance"]
        previous = data["previous_week"]["personal_finance"]
        if not data["previous_week"].get("records", {}).get("transactions"):
            return "Não há transações suficientes da semana passada para uma comparação factual."
        income_delta = current["income"] - previous["income"]
        expense_delta = current["expenses"] - previous["expenses"]
        income_word = "acima" if income_delta >= 0 else "abaixo"
        expense_word = "maiores" if expense_delta >= 0 else "menores"
        return (f"Suas entradas estão R$ {abs(income_delta):.2f} {income_word} da semana passada. "
                f"Seus gastos estão R$ {abs(expense_delta):.2f} {expense_word}.")
    return _result(_client().weekly_summary, message)


def register(registry) -> None:
    specs = [
        ("get_rotina_summary", "Consulta o resumo geral do ROTINA.", {}, get_rotina_summary, RiskLevel.LOW),
        ("get_today_tasks", "Lista as tarefas de hoje no ROTINA.", {}, get_today_tasks, RiskLevel.LOW),
        ("add_task", "Adiciona uma tarefa no ROTINA pela API.", {"title": {"type": "string"}, "date": {"type": "string"}}, add_task, RiskLevel.LOW),
        ("complete_task", "Marca uma tarefa do ROTINA como concluída.", {"title_or_id": {"type": "string"}}, complete_task, RiskLevel.LOW),
        ("add_income", "Registra uma entrada financeira pessoal no ROTINA.", {"amount": {"type": "number"}, "description": {"type": "string"}}, add_income, RiskLevel.LOW),
        ("add_expense", "Registra uma despesa financeira pessoal no ROTINA.", {"amount": {"type": "number"}, "description": {"type": "string"}}, add_expense, RiskLevel.LOW),
        ("get_financial_summary", "Consulta entradas, gastos e saldo pessoais da semana, sem misturar negócios.", {}, get_financial_summary, RiskLevel.LOW),
        ("get_business_summary", "Consulta receita, custos e lucro de negócios da semana.", {}, get_business_summary, RiskLevel.LOW),
        ("get_weekly_finance", "Consulta o financeiro semanal pessoal e de negócios em blocos separados.", {}, get_weekly_finance, RiskLevel.LOW),
        ("get_weekly_productivity", "Consulta a produtividade semanal baseada em tarefas com data.", {}, get_weekly_productivity, RiskLevel.LOW),
        ("compare_weekly_finance", "Compara entradas e gastos pessoais com a semana anterior quando há dados.", {}, compare_weekly_finance, RiskLevel.LOW),
    ]
    required = {"add_task": ["title"], "complete_task": ["title_or_id"],
                "add_income": ["amount"], "add_expense": ["amount"]}
    for name, description, properties, handler, risk in specs:
        registry.register(Tool(name=name, description=description,
                               parameters={"type": "object", "properties": properties,
                                           "required": required.get(name, [])},
                               risk_level=risk, handler=handler))
