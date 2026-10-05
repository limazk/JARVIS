from datetime import datetime, timezone

from server import weekly_summary


def _state():
    return {
        "transactions": [
            {"type": "in", "amount": 700, "date": "2026-09-21"},
            {"type": "out", "amount": 180, "date": "2026-09-27T23:59:59+00:00"},
            {"type": "in", "amount": 900, "date": "2026-09-28T00:00:00+00:00"},
            {"type": "out", "amount": 100, "date": "2026-09-30"},
            {"type": "in", "amount": 999, "date": "2026-10-05"},
        ],
        "bizEntries": [
            {"type": "revenue", "amount": 650, "date": "2026-09-29"},
            {"type": "cost", "amount": 210, "date": "2026-09-30"},
            {"type": "revenue", "amount": 300, "date": "2026-09-22"},
            {"type": "cost", "amount": 50, "date": "2026-09-23"},
        ],
        "tasks": [
            {"title": "A", "date": "2026-09-28", "doneDates": ["2026-09-28"]},
            {"title": "B", "date": "2026-09-30", "doneDates": []},
            {"title": "Anterior", "date": "2026-09-22", "doneDates": ["2026-09-22"]},
            {"title": "Sem data", "doneDates": ["2026-09-29"]},
        ],
    }


def test_week_boundaries_and_previous_week():
    result = weekly_summary(_state(), datetime(2026, 9, 30, 12, tzinfo=timezone.utc))
    assert result["period"]["start"].startswith("2026-09-28T00:00:00")
    assert result["previous_week"]["period"]["start"].startswith("2026-09-21T00:00:00")
    assert result["previous_week"]["period"]["end"].startswith("2026-09-27T23:59:59.999999")


def test_personal_finance_income_expense_net_and_previous():
    result = weekly_summary(_state(), datetime(2026, 9, 30, 12, tzinfo=timezone.utc))
    assert result["personal_finance"] == {"income": 900.0, "expenses": 100.0, "net": 800.0}
    assert result["previous_week"]["personal_finance"] == {"income": 700.0, "expenses": 180.0, "net": 520.0}


def test_business_revenue_cost_profit_are_separate():
    result = weekly_summary(_state(), datetime(2026, 9, 30, 12, tzinfo=timezone.utc))
    assert result["business"] == {"revenue": 650.0, "cost": 210.0, "profit": 440.0}
    assert result["previous_week"]["business"] == {"revenue": 300.0, "cost": 50.0, "profit": 250.0}
    # A receita do negócio não é somada à entrada pessoal potencialmente duplicada.
    assert result["personal_finance"]["income"] == 900.0


def test_productivity_only_uses_tasks_with_period_date():
    result = weekly_summary(_state(), datetime(2026, 9, 30, 12, tzinfo=timezone.utc))
    assert result["productivity"] == {"tasks": 2, "completed": 1, "pending": 1, "completion_pct": 50.0}
    assert result["previous_week"]["productivity"]["tasks"] == 1
    assert result["previous_week"]["productivity"]["completion_pct"] == 100.0
