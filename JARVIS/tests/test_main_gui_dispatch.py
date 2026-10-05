"""
Testes de main.py::run_gui_mode — só a lógica de "qual interface abrir",
sem abrir nenhuma janela de verdade (nem pywebview, nem CustomTkinter):
substitui `interface_web.webview_app` e `interface.app` por módulos fake
em sys.modules, no mesmo padrão usado pelas outras libs opcionais deste
projeto (ver test_tray.py, test_spotify.py).
"""
from __future__ import annotations

import sys
import types

import pytest

import main


@pytest.fixture(autouse=True)
def _cleanup_fake_modules():
    yield
    sys.modules.pop("interface_web.webview_app", None)
    sys.modules.pop("interface.app", None)


def _install_fake_webview_app(*, available: bool, raise_on_run: bool = False):
    calls = {"run_app": []}
    fake = types.ModuleType("interface_web.webview_app")
    fake.available = lambda: available

    def _run_app(minimized=False):
        calls["run_app"].append(minimized)
        if raise_on_run:
            raise RuntimeError("WebView2 Runtime não encontrado (simulado)")

    fake.run_app = _run_app
    sys.modules["interface_web.webview_app"] = fake
    return calls


def _install_fake_ctk_app():
    calls = {"run_app": []}
    fake = types.ModuleType("interface.app")
    fake.run_app = lambda minimized=False: calls["run_app"].append(minimized)
    sys.modules["interface.app"] = fake
    return calls


def test_usa_pywebview_quando_disponivel():
    web_calls = _install_fake_webview_app(available=True)
    ctk_calls = _install_fake_ctk_app()

    main.run_gui_mode(minimized=True)

    assert web_calls["run_app"] == [True]
    assert ctk_calls["run_app"] == []  # nunca chega a cair pro CustomTkinter


def test_cai_para_customtkinter_quando_pywebview_nao_disponivel():
    web_calls = _install_fake_webview_app(available=False)
    ctk_calls = _install_fake_ctk_app()

    main.run_gui_mode(minimized=False)

    assert web_calls["run_app"] == []  # nem chega a tentar abrir a janela
    assert ctk_calls["run_app"] == [False]


def test_cai_para_customtkinter_quando_pywebview_falha_ao_abrir():
    web_calls = _install_fake_webview_app(available=True, raise_on_run=True)
    ctk_calls = _install_fake_ctk_app()

    main.run_gui_mode(minimized=False)

    assert web_calls["run_app"] == [False]  # tentou, mas quebrou (ex.: sem WebView2 Runtime)
    assert ctk_calls["run_app"] == [False]  # caiu pro fallback mesmo assim


def test_sem_nenhuma_interface_instalada_nao_quebra(capsys):
    sys.modules.pop("interface_web", None)
    import builtins

    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name in {"interface_web", "interface.app"} or name.startswith("interface_web."):
            raise ImportError(f"{name} indisponível (simulado)")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = _blocked_import
    try:
        main.run_gui_mode()
    finally:
        builtins.__import__ = real_import

    assert "ETAPA 6" in capsys.readouterr().out
