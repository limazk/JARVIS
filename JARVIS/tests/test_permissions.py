"""Testes do PermissionManager (core/permissions.py) — seção 28 do spec."""
import pytest

from core.permissions import PermissionDenied, PermissionManager, RiskLevel


def test_low_risk_executa_sem_perguntar():
    manager = PermissionManager(confirm_callback=lambda message: False)
    assert manager.check("qualquer_tool", RiskLevel.LOW, "descrição") is True


def test_medium_risk_pede_confirmacao_e_aceita():
    manager = PermissionManager(confirm_callback=lambda message: True)
    assert manager.check("tool", RiskLevel.MEDIUM, "descrição") is True


def test_medium_risk_negado_lanca_excecao():
    manager = PermissionManager(confirm_callback=lambda message: False)
    with pytest.raises(PermissionDenied):
        manager.check("tool", RiskLevel.MEDIUM, "descrição")


def test_high_risk_tambem_exige_confirmacao():
    manager = PermissionManager(confirm_callback=lambda message: False)
    with pytest.raises(PermissionDenied):
        manager.check("tool", RiskLevel.HIGH, "descrição")


def test_critical_bloqueado_por_padrao(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "allow_critical_actions", False)
    manager = PermissionManager(confirm_callback=lambda message: True)
    with pytest.raises(PermissionDenied):
        manager.check("tool_critica", RiskLevel.CRITICAL, "descrição")


def test_critical_liberado_quando_configurado_explicitamente(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "allow_critical_actions", True)
    manager = PermissionManager(confirm_callback=lambda message: True)
    assert manager.check("tool_critica", RiskLevel.CRITICAL, "descrição") is True
