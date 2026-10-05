"""
Testes de config/settings.py::save_env_values / reload_settings — parte
da ETAPA EXE-1 (tela de configuração da interface gráfica, que salva a
chave de API sem exigir edição manual do .env).
"""
from __future__ import annotations

import dataclasses

import pytest

import config.settings as settings_module


@pytest.fixture(autouse=True)
def _restore_settings_singleton():
    """
    reload_settings() muda o objeto `settings` compartilhado de verdade
    (não é um monkeypatch reversível sozinho) — sem isso, o teste de
    reload aqui vazaria LLM_PROVIDER=groq pros testes que rodarem depois
    dele na mesma sessão do pytest.
    """
    original = {f.name: getattr(settings_module.settings, f.name) for f in dataclasses.fields(settings_module.settings)}
    yield
    for name, value in original.items():
        setattr(settings_module.settings, name, value)


def test_save_env_values_cria_env_a_partir_do_example(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "BASE_DIR", tmp_path)
    (tmp_path / ".env.example").write_text("LLM_PROVIDER=claude\nANTHROPIC_API_KEY=\n", encoding="utf-8")

    settings_module.save_env_values({"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "abc123"})

    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=gemini" in content
    assert "GEMINI_API_KEY=abc123" in content
    # Chave que já existia no example e não foi tocada continua lá.
    assert "ANTHROPIC_API_KEY=" in content


def test_save_env_values_atualiza_chave_existente_sem_duplicar(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "BASE_DIR", tmp_path)
    (tmp_path / ".env").write_text("LLM_PROVIDER=claude\nGEMINI_API_KEY=velha\n", encoding="utf-8")

    settings_module.save_env_values({"GEMINI_API_KEY": "nova"})

    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert content.count("GEMINI_API_KEY=") == 1
    assert "GEMINI_API_KEY=nova" in content
    assert "velha" not in content


def test_reload_settings_atualiza_objeto_settings_em_memoria(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "BASE_DIR", tmp_path)
    (tmp_path / ".env").write_text("LLM_PROVIDER=groq\nGROQ_API_KEY=xyz\n", encoding="utf-8")

    settings_module.reload_settings()

    assert settings_module.settings.llm_provider == "groq"
    assert settings_module.settings.groq_api_key == "xyz"
