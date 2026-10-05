"""
Testes do ícone na bandeja do Windows (interface/tray.py) — parte de
"usar o Jarvis só como .exe, feito um app de verdade".

`pystray` não está disponível neste sandbox de testes (sem acesso ao
índice do PyPI) — o caminho "sem pystray instalado" já é coberto de
graça por isso (nada precisa ser injetado); o caminho "com pystray"
injeta um módulo fake mínimo em sys.modules, no mesmo padrão usado
pelas outras libs opcionais deste projeto (ver test_spotify.py,
test_wake_word.py).
"""
from __future__ import annotations

import sys
import types

from interface.tray import TrayIcon


def test_start_sem_pystray_instalado_retorna_false():
    sys.modules.pop("pystray", None)  # garante que não sobrou de outro teste

    tray = TrayIcon(on_open=lambda: None, on_quit=lambda: None)

    assert tray.start() is False


def test_stop_sem_nunca_ter_iniciado_nao_quebra():
    tray = TrayIcon(on_open=lambda: None, on_quit=lambda: None)

    tray.stop()  # não deve levantar exceção mesmo sem start() ter sido chamado


def test_start_com_pystray_disponivel_sobe_o_icone():
    fake_pystray = types.ModuleType("pystray")

    created_icons = []

    class _FakeMenuItem:
        def __init__(self, text, action, default=False):
            self.text = text
            self.action = action
            self.default = default

    class _FakeMenu:
        def __init__(self, *items):
            self.items = items

    class _FakeIcon:
        def __init__(self, name, image, title, menu):
            self.name = name
            self.image = image
            self.title = title
            self.menu = menu
            self.ran = False
            self.stopped = False
            created_icons.append(self)

        def run(self):
            self.ran = True

        def stop(self):
            self.stopped = True

    fake_pystray.MenuItem = _FakeMenuItem
    fake_pystray.Menu = _FakeMenu
    fake_pystray.Icon = _FakeIcon
    sys.modules["pystray"] = fake_pystray

    try:
        tray = TrayIcon(on_open=lambda: None, on_quit=lambda: None)
        ok = tray.start()

        assert ok is True
        assert len(created_icons) == 1
        # dá um instante pra thread do ícone fake rodar (run() é instantâneo)
        import time

        time.sleep(0.05)
        assert created_icons[0].ran is True

        tray.stop()
        assert created_icons[0].stopped is True
    finally:
        sys.modules.pop("pystray", None)


def test_start_com_icone_ilegivel_retorna_false(monkeypatch):
    fake_pystray = types.ModuleType("pystray")
    fake_pystray.MenuItem = lambda *a, **k: None
    fake_pystray.Menu = lambda *a, **k: None
    fake_pystray.Icon = lambda *a, **k: None
    sys.modules["pystray"] = fake_pystray

    import interface.tray as tray_mod
    from config.settings import settings

    monkeypatch.setattr(settings, "base_dir", settings.base_dir / "pasta-que-nao-existe")

    try:
        tray = tray_mod.TrayIcon(on_open=lambda: None, on_quit=lambda: None)
        assert tray.start() is False
    finally:
        sys.modules.pop("pystray", None)
