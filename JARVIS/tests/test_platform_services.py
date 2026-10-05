from __future__ import annotations

import subprocess

from platform_services import get_platform_services
from platform_services.linux import LinuxServices


def test_platform_detection():
    assert get_platform_services("Linux").name == "linux"
    assert get_platform_services("Windows").name == "windows"


def test_linux_open_path_usa_xdg_open(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("platform_services.linux.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("platform_services.linux.subprocess.Popen", lambda argv, **kwargs: calls.append(argv))
    result = LinuxServices().open_path(tmp_path)
    assert result.success
    assert calls[0][0] == "/usr/bin/xdg-open"


def test_linux_open_url_usa_xdg_open(monkeypatch):
    calls = []
    monkeypatch.setattr("platform_services.linux.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("platform_services.linux.subprocess.Popen", lambda argv, **kwargs: calls.append(argv))
    assert LinuxServices().open_url("https://example.com").success
    assert calls[0][-1] == "https://example.com"


def test_linux_application_lookup_missing(monkeypatch):
    monkeypatch.setattr("platform_services.linux.shutil.which", lambda name: None)
    result = LinuxServices().open_application("nao-existe")
    assert not result.success
    assert "não encontrei" in result.message.lower()


def test_volume_prefere_wpctl_e_fallback_pactl(monkeypatch):
    service = LinuxServices()
    monkeypatch.setattr("platform_services.linux.shutil.which", lambda name: "/usr/bin/pactl" if name == "pactl" else None)
    calls = []
    monkeypatch.setattr("platform_services.linux.subprocess.run",
                        lambda argv, **kwargs: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", ""))
    result = service.set_volume(42)
    assert result.success and result.data["backend"] == "pactl"
    assert calls[0][0] == "pactl"


def test_lock_session_prioriza_loginctl(monkeypatch):
    calls = []
    monkeypatch.setattr("platform_services.linux.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("platform_services.linux.subprocess.run",
                        lambda argv, **kwargs: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", ""))
    assert LinuxServices().lock_session().success
    assert calls[0][0].endswith("loginctl")
