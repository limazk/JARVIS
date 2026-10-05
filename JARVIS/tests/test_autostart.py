"""
Testes do início automático com o Windows (interface/autostart.py) —
parte de "usar o Jarvis só como .exe, feito um app de verdade".

`winreg` só existe no Windows, então este sandbox de testes (Linux)
não o tem de verdade — os testes do caminho "suportado" injetam um
módulo `winreg` fake mínimo em sys.modules (mesmo padrão usado em
test_spotify.py/test_discord_bot.py pra libs que não estão disponíveis
aqui), e sempre monkeypatcham `autostart.supported()` pra simular
"estamos dentro do Jarvis.exe no Windows" sem depender do SO real.
"""
from __future__ import annotations

import sys
import types

import pytest

from interface import autostart


def _install_fake_winreg():
    fake = types.ModuleType("winreg")
    fake.HKEY_CURRENT_USER = "HKCU"
    fake.KEY_READ = 1
    fake.KEY_SET_VALUE = 2
    fake.REG_SZ = 1

    store: dict[str, str] = {}
    fake._store = store  # type: ignore[attr-defined]

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _open_key(hive, path, reserved=0, access=0):
        return _Key()

    def _query_value_ex(key, name):
        if name not in store:
            raise FileNotFoundError(name)
        return store[name], fake.REG_SZ

    def _set_value_ex(key, name, reserved, value_type, value):
        store[name] = value

    def _delete_value(key, name):
        if name not in store:
            raise FileNotFoundError(name)
        del store[name]

    fake.OpenKey = _open_key
    fake.QueryValueEx = _query_value_ex
    fake.SetValueEx = _set_value_ex
    fake.DeleteValue = _delete_value
    sys.modules["winreg"] = fake
    return fake


@pytest.fixture
def _fake_winreg():
    fake = _install_fake_winreg()
    yield fake
    sys.modules.pop("winreg", None)


def test_nao_suportado_fora_do_exe_empacotado(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert autostart.supported() is False


def test_nao_suportado_fora_do_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert autostart.supported() is False


def test_is_enabled_false_quando_nao_suportado(monkeypatch):
    monkeypatch.setattr(autostart, "supported", lambda: False)

    assert autostart.is_enabled() is False


def test_set_enabled_fora_do_suportado_levanta_erro_amigavel(monkeypatch):
    monkeypatch.setattr(autostart, "supported", lambda: False)

    with pytest.raises(RuntimeError, match="Jarvis.exe"):
        autostart.set_enabled(True)


def test_set_enabled_liga_e_is_enabled_reflete(monkeypatch, _fake_winreg):
    monkeypatch.setattr(autostart, "supported", lambda: True)
    monkeypatch.setattr(sys, "executable", r"C:\Jarvis\Jarvis.exe")

    assert autostart.is_enabled() is False

    autostart.set_enabled(True)

    assert autostart.is_enabled() is True
    assert _fake_winreg._store["Jarvis"] == '"C:\\Jarvis\\Jarvis.exe" --minimized'


def test_set_enabled_desliga_remove_do_registro(monkeypatch, _fake_winreg):
    monkeypatch.setattr(autostart, "supported", lambda: True)
    monkeypatch.setattr(sys, "executable", r"C:\Jarvis\Jarvis.exe")

    autostart.set_enabled(True)
    assert autostart.is_enabled() is True

    autostart.set_enabled(False)
    assert autostart.is_enabled() is False
    assert "Jarvis" not in _fake_winreg._store


def test_set_enabled_desligar_sem_estar_ligado_nao_quebra(monkeypatch, _fake_winreg):
    monkeypatch.setattr(autostart, "supported", lambda: True)

    autostart.set_enabled(False)  # não deve levantar mesmo nunca tendo sido ligado

    assert autostart.is_enabled() is False
