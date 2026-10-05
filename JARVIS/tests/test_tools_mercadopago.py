"""
Testes da integração com o Mercado Pago (tools/mercadopago.py) —
vendas recentes, criação de cobrança e saldo (relatório de liquidação).

`requests` está disponível de verdade neste sandbox, então mockamos só
os métodos usados (`requests.get`/`requests.post`) via monkeypatch, em
vez de instalar um módulo fake inteiro (diferente de tests/test_spotify.py,
que precisa disso porque `spotipy` não está instalado aqui).
"""
from __future__ import annotations

import time

import pytest
import requests

from config.settings import settings
from core.permissions import PermissionManager, RiskLevel
from tools import mercadopago
from tools.registry import ToolRegistry


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", raise_exc=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json_data


@pytest.fixture(autouse=True)
def _token():
    """A maioria dos testes precisa de um token configurado; os que não precisam limpam sozinhos."""
    original = settings.mercadopago_access_token
    settings.mercadopago_access_token = "TEST-token-123"
    yield
    settings.mercadopago_access_token = original


# ---------------------------------------------------------------- sem token


def test_vendas_recentes_sem_token_e_honesto(monkeypatch):
    monkeypatch.setattr(settings, "mercadopago_access_token", "")
    result = mercadopago.mercadopago_vendas_recentes()
    assert result.success is False
    assert "mercadopago_access_token" in result.message.lower()


def test_criar_cobranca_sem_token_e_honesto(monkeypatch):
    monkeypatch.setattr(settings, "mercadopago_access_token", "")
    result = mercadopago.mercadopago_criar_cobranca("Produto X", 10.0)
    assert result.success is False
    assert "mercadopago_access_token" in result.message.lower()


def test_saldo_sem_token_e_honesto(monkeypatch):
    monkeypatch.setattr(settings, "mercadopago_access_token", "")
    result = mercadopago.mercadopago_saldo()
    assert result.success is False
    assert "mercadopago_access_token" in result.message.lower()


# ---------------------------------------------------------- vendas recentes


def test_vendas_recentes_sem_resultados(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(json_data={"results": []}))

    result = mercadopago.mercadopago_vendas_recentes(dias=5)

    assert result.success is True
    assert "nenhuma venda" in result.message.lower()
    assert result.data == {"vendas": []}


def test_vendas_recentes_resume_aprovadas_e_total(monkeypatch):
    vendas = [
        {"status": "approved", "transaction_amount": 100.0, "currency_id": "BRL", "description": "Plano Pro"},
        {"status": "pending", "transaction_amount": 50.0, "currency_id": "BRL", "description": "Plano Básico"},
        {"status": "approved", "transaction_amount": 25.5, "currency_id": "BRL", "description": "Extra"},
    ]
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(json_data={"results": vendas}))

    result = mercadopago.mercadopago_vendas_recentes(dias=7)

    assert result.success is True
    assert "3 venda(s)" in result.message
    assert "2 aprovada(s)" in result.message
    assert "125.50" in result.message
    assert "Plano Pro" in result.message
    assert "pendente" in result.message.lower()
    assert len(result.data["vendas"]) == 3


def test_vendas_recentes_erro_de_rede_e_honesto(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("sem internet")

    monkeypatch.setattr(requests, "get", _boom)

    result = mercadopago.mercadopago_vendas_recentes()

    assert result.success is False
    assert "não consegui consultar" in result.message.lower()


# ---------------------------------------------------------- criar cobrança


def test_criar_cobranca_devolve_link(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **k: _FakeResponse(json_data={"init_point": "https://mpago.la/abc123"}),
    )

    result = mercadopago.mercadopago_criar_cobranca("Consultoria", 199.9, descricao="1h de consultoria")

    assert result.success is True
    assert "https://mpago.la/abc123" in result.message
    assert "199.90" in result.message


def test_criar_cobranca_sem_link_na_resposta_e_honesto(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(json_data={}))

    result = mercadopago.mercadopago_criar_cobranca("Produto Y", 10.0)

    assert result.success is False
    assert "não devolveu um link" in result.message.lower()


def test_criar_cobranca_exige_confirmacao_via_permission_manager(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **k: _FakeResponse(json_data={"init_point": "https://mpago.la/xyz"}),
    )

    registry = ToolRegistry()
    permissions = PermissionManager(confirm_callback=lambda message: False)
    mercadopago.register(registry, permissions)

    tool = registry.get("mercadopago_criar_cobranca")
    assert tool.risk_level == RiskLevel.MEDIUM

    result = tool.execute(titulo="Produto Z", valor=15.0)

    assert result.success is False
    assert "cancelada" in result.message.lower()


def test_criar_cobranca_prossegue_quando_confirmado(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **k: _FakeResponse(json_data={"init_point": "https://mpago.la/ok"}),
    )

    registry = ToolRegistry()
    permissions = PermissionManager(confirm_callback=lambda message: True)
    mercadopago.register(registry, permissions)

    result = registry.get("mercadopago_criar_cobranca").execute(titulo="Produto Z", valor=15.0)

    assert result.success is True
    assert "https://mpago.la/ok" in result.message


# -------------------------------------------------------------------- saldo


def test_saldo_soma_valores_liquidados(monkeypatch):
    monkeypatch.setattr(mercadopago.time, "sleep", lambda _s: None)

    def _fake_post(url, **_k):
        assert "settlement_report" in url
        return _FakeResponse(status_code=202)

    def _fake_get(url, **_k):
        if url.endswith("/list"):
            return _FakeResponse(json_data={"response": [{"file_name": "relatorio123.csv"}]})
        assert url.endswith("relatorio123.csv")
        csv_text = "SETTLEMENT_NET_AMOUNT,OTHER\n100.50,x\n49.25,y\n"
        return _FakeResponse(text=csv_text)

    monkeypatch.setattr(requests, "post", _fake_post)
    monkeypatch.setattr(requests, "get", _fake_get)

    result = mercadopago.mercadopago_saldo(dias=30)

    assert result.success is True
    assert "149.75" in result.message
    assert result.data["total"] == pytest.approx(149.75)


def test_saldo_relatorio_nunca_fica_pronto_e_honesto(monkeypatch):
    monkeypatch.setattr(mercadopago.time, "sleep", lambda _s: None)
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(status_code=202))
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(json_data={"response": []}))

    result = mercadopago.mercadopago_saldo(dias=10)

    assert result.success is False
    assert "ainda está gerando" in result.message.lower()


def test_saldo_sem_movimentacao(monkeypatch):
    monkeypatch.setattr(mercadopago.time, "sleep", lambda _s: None)
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(status_code=202))

    def _fake_get(url, **_k):
        if url.endswith("/list"):
            return _FakeResponse(json_data={"response": [{"file_name": "vazio.csv"}]})
        return _FakeResponse(text="SETTLEMENT_NET_AMOUNT\n")

    monkeypatch.setattr(requests, "get", _fake_get)

    result = mercadopago.mercadopago_saldo(dias=30)

    assert result.success is True
    assert "nenhuma movimentação" in result.message.lower()


# -------------------------------------------------------------- registro


def test_register_adiciona_as_tres_ferramentas():
    registry = ToolRegistry()
    mercadopago.register(registry)

    nomes = {t.name for t in registry.all()}
    assert {"mercadopago_vendas_recentes", "mercadopago_criar_cobranca", "mercadopago_saldo"} <= nomes

    vendas_tool = registry.get("mercadopago_vendas_recentes")
    saldo_tool = registry.get("mercadopago_saldo")
    assert vendas_tool.risk_level == RiskLevel.LOW
    assert saldo_tool.risk_level == RiskLevel.LOW
