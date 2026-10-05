"""
Testes de config/settings.py — BASE_DIR precisa apontar pra pasta do
.exe (não pra uma pasta temporária) quando o Jarvis roda empacotado via
PyInstaller (sys.frozen=True). Sem isso, .env/banco/logs "sumiriam" a
cada vez que o .exe fosse fechado (parte da ETAPA EXE-2).

Testa `_compute_base_dir()` isoladamente (sem `importlib.reload` do
módulo inteiro) de propósito: recarregar config/settings.py criaria um
SEGUNDO objeto `settings`, diferente do que o resto do sistema (já
importado antes) está usando — os dois ficariam dessincronizados e
mudanças feitas num não apareceriam no outro, quebrando outros testes.
"""
from __future__ import annotations

import sys

from config.settings import BASE_DIR, _compute_base_dir


def test_base_dir_normal_e_a_raiz_do_projeto():
    # Em modo normal (não empacotado), BASE_DIR é a pasta que contém main.py.
    assert (BASE_DIR / "main.py").exists()


def test_base_dir_frozen_usa_pasta_do_executavel(monkeypatch, tmp_path):
    fake_exe = tmp_path / "Jarvis.exe"
    fake_exe.write_text("fake")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    assert _compute_base_dir() == tmp_path


def test_base_dir_sem_frozen_ignora_sys_executable(monkeypatch):
    # Garantia extra: sem sys.frozen, o valor de sys.executable (que em
    # modo normal é o python.exe, não o Jarvis) não deve influenciar nada.
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert _compute_base_dir() == BASE_DIR
