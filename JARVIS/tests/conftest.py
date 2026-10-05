"""
Configuração compartilhada dos testes.

Garante que a raiz do projeto está no sys.path (para `import core...`,
`import tools...` funcionarem independente de onde o pytest for
chamado) e isola cada teste em um banco SQLite temporário, para não
misturar dados de teste com o banco de dados real do usuário.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "test_jarvis.db")
    yield
