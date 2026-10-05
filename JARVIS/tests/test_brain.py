"""
Testes do "cérebro" (core/brain.py) — provedores de IA grátis (Gemini,
Groq) além do já existente Ollama local, e do roteamento por
LLM_PROVIDER (seção 4 do spec).

Não testamos chamadas reais de API (isso exigiria chave e internet).
O que importa aqui é: (1) sem chave configurada, cada provedor falha
de forma honesta em vez de quebrar; (2) get_llm_provider() escolhe a
classe certa para cada valor de LLM_PROVIDER.
"""
from __future__ import annotations

from core.brain import (
    ClaudeProvider,
    GeminiProvider,
    GroqProvider,
    LocalProvider,
    OpenAIProvider,
    get_llm_provider,
)


def test_gemini_sem_chave_e_honesto(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "gemini_api_key", "")
    provider = GeminiProvider()
    assert provider.available is False
    decision = provider.decide("system", [], [])
    assert decision.kind == "text"
    assert "gemini" in decision.text.lower()


def test_groq_sem_chave_e_honesto(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "groq_api_key", "")
    provider = GroqProvider()
    assert provider.available is False
    decision = provider.decide("system", [], [])
    assert decision.kind == "text"
    assert "groq" in decision.text.lower()


def test_get_llm_provider_reconhece_todos_os_provedores(monkeypatch):
    from config.settings import settings

    esperado = {
        "claude": ClaudeProvider,
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
        "groq": GroqProvider,
        "local": LocalProvider,
    }
    for nome, classe in esperado.items():
        monkeypatch.setattr(settings, "llm_provider", nome)
        assert isinstance(get_llm_provider(), classe)


def test_get_llm_provider_cai_para_claude_se_valor_desconhecido(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "llm_provider", "algo-inexistente")
    assert isinstance(get_llm_provider(), ClaudeProvider)
