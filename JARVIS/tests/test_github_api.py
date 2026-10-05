"""Testes da integração com a API do GitHub (tools/github.py) — sem token configurado."""
from tools.github import list_my_repos


def test_list_my_repos_sem_token_e_honesto(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "github_token", "")
    result = list_my_repos()
    assert result.success is False
    assert "github_token" in result.message.lower()
