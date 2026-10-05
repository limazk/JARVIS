#!/usr/bin/env python3
"""Diagnóstico somente leitura; nunca imprime chaves ou tokens."""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config.settings import settings  # noqa: E402
from core.brain import LocalProvider, OllamaHealth  # noqa: E402
from integrations.rotina import RotinaClient, RotinaError  # noqa: E402


def _line(ok: bool, label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"[{'OK' if ok else 'ERRO'}] {label}{suffix}")


def _systemd_status() -> tuple[bool, str]:
    unit = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "systemd/user/jarvis.service"
    if not unit.exists():
        return False, "unidade não instalada"
    try:
        result = subprocess.run(["systemctl", "--user", "is-enabled", "jarvis.service"],
                                capture_output=True, text=True, timeout=3)
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def run_doctor() -> int:
    print("JARVIS DOCTOR\n")
    linux = platform.system() == "Linux"
    distro = ""
    try:
        distro = Path("/etc/os-release").read_text(encoding="utf-8").lower()
    except OSError:
        pass
    kali = linux and ("id=kali" in distro or "kali" in distro)
    _line(kali, "Kali Linux" if kali else f"Sistema {platform.system()}", platform.platform())
    _line(sys.version_info >= (3, 10), f"Python {platform.python_version()}", sys.executable)
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    _line(in_venv, "venv", sys.prefix if in_venv else "ambiente virtual não ativo")

    try:
        import pyaudio

        audio = pyaudio.PyAudio()
        inputs = sum(1 for i in range(audio.get_device_count()) if audio.get_device_info_by_index(i).get("maxInputChannels", 0) > 0)
        outputs = sum(1 for i in range(audio.get_device_count()) if audio.get_device_info_by_index(i).get("maxOutputChannels", 0) > 0)
        audio.terminate()
        _line(inputs > 0, "Microphone", f"{inputs} dispositivo(s) de entrada")
        _line(outputs > 0, "Audio output", f"{outputs} dispositivo(s) de saída")
    except Exception as exc:
        _line(False, "Microphone", str(exc))
        backend = "wpctl" if shutil.which("wpctl") else "pactl" if shutil.which("pactl") else ""
        if backend:
            command = [backend, "status"] if backend == "wpctl" else [backend, "info"]
            try:
                probe = subprocess.run(command, capture_output=True, text=True, timeout=3)
                _line(probe.returncode == 0, "Audio output", f"backend {backend} respondeu" if probe.returncode == 0 else f"backend {backend} sem servidor de áudio")
            except (OSError, subprocess.SubprocessError) as audio_exc:
                _line(False, "Audio output", str(audio_exc))
        else:
            _line(False, "Audio output", "wpctl/pactl não encontrados")

    openwakeword_available = importlib.util.find_spec("openwakeword") is not None
    if openwakeword_available:
        _line(True, "Wake engine", "openWakeWord disponível")
    elif settings.wake_word_engine.strip().lower() in {"auto", "stt"}:
        _line(True, "Wake engine", "STT ativo; openWakeWord opcional neste Python")
    else:
        _line(False, "Wake engine", "openWakeWord solicitado, mas pacote indisponível")
    provider = LocalProvider()
    server_state, server_detail = provider.server_status()
    state, detail = provider.health_check()
    _line(server_state == OllamaHealth.ONLINE, "Ollama", server_detail)
    _line(state == OllamaHealth.MODEL_READY, settings.local_llm_model, detail)
    try:
        health = RotinaClient(timeout=2).health()
        _line(health.get("status") == "ok", "ROTINA API", settings.rotina_url)
    except RotinaError as exc:
        _line(False, "ROTINA API", str(exc))
    systemd_ok, systemd_detail = _systemd_status()
    _line(systemd_ok, "systemd service", systemd_detail)
    writable = os.access(settings.log_path.parent, os.W_OK) and os.access(settings.db_path.parent, os.W_OK)
    _line(writable, "permissions", "pastas de logs e database")
    return 0 if state == OllamaHealth.MODEL_READY and writable else 1


if __name__ == "__main__":
    raise SystemExit(run_doctor())
