"""Implementação Linux, sem shell e com fallbacks explícitos."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from platform_services.base import PlatformResult, PlatformServices


class LinuxServices(PlatformServices):
    name = "linux"

    @staticmethod
    def _spawn(argv: Sequence[str], label: str) -> PlatformResult:
        executable = shutil.which(argv[0])
        if not executable:
            return PlatformResult(False, f"Não encontrei '{argv[0]}' instalado no sistema.")
        try:
            subprocess.Popen([executable, *argv[1:]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return PlatformResult(True, label)
        except OSError as exc:
            return PlatformResult(False, f"Não consegui iniciar '{argv[0]}': {exc}")

    def open_application(self, command: str | Sequence[str], display_name: str = "aplicativo") -> PlatformResult:
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        if not argv:
            return PlatformResult(False, "Comando de aplicativo vazio.")
        result = self._spawn(argv, f"Abrindo {display_name}.")
        return result

    def open_path(self, path: str | Path) -> PlatformResult:
        target = Path(path).expanduser()
        if not target.exists():
            return PlatformResult(False, f"O caminho não existe: {target}")
        return self._spawn(["xdg-open", str(target)], f"Abrindo {target}.")

    def open_url(self, url: str) -> PlatformResult:
        return self._spawn(["xdg-open", url], "Abrindo o endereço no navegador.")

    @staticmethod
    def _volume_backend() -> str | None:
        if shutil.which("wpctl"):
            return "wpctl"
        if shutil.which("pactl"):
            return "pactl"
        return None

    def set_volume(self, level: int) -> PlatformResult:
        level = max(0, min(100, int(level)))
        backend = self._volume_backend()
        if not backend:
            return PlatformResult(False, "Nenhum backend de volume encontrado (wpctl ou pactl).")
        cmd = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{level}%"] if backend == "wpctl" else [
            "pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=5)
            return PlatformResult(True, f"Volume ajustado para {level}%.", {"backend": backend, "level": level})
        except (OSError, subprocess.SubprocessError) as exc:
            return PlatformResult(False, f"Não consegui ajustar o volume com {backend}: {exc}")

    def get_volume(self) -> PlatformResult:
        backend = self._volume_backend()
        if not backend:
            return PlatformResult(False, "Nenhum backend de volume encontrado (wpctl ou pactl).")
        cmd = ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"] if backend == "wpctl" else [
            "pactl", "get-sink-volume", "@DEFAULT_SINK@"
        ]
        try:
            output = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=5).stdout
            match = re.search(r"(\d+)%", output)
            if match:
                level = int(match.group(1))
            else:
                scalar = re.search(r"Volume:\s+([0-9.]+)", output)
                if not scalar:
                    raise ValueError("formato de saída desconhecido")
                level = round(float(scalar.group(1)) * 100)
            muted = "MUTED" in output.upper()
            return PlatformResult(True, f"Volume em {level}%.", {"backend": backend, "level": level, "muted": muted})
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return PlatformResult(False, f"Não consegui consultar o volume com {backend}: {exc}")

    def mute_volume(self) -> PlatformResult:
        backend = self._volume_backend()
        if not backend:
            return PlatformResult(False, "Nenhum backend de volume encontrado (wpctl ou pactl).")
        cmd = ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"] if backend == "wpctl" else [
            "pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=5)
            return PlatformResult(True, "Áudio mutado.", {"backend": backend})
        except (OSError, subprocess.SubprocessError) as exc:
            return PlatformResult(False, f"Não consegui mutar o áudio com {backend}: {exc}")

    def lock_session(self) -> PlatformResult:
        attempts = (["loginctl", "lock-session"], ["xdg-screensaver", "lock"])
        errors = []
        for command in attempts:
            executable = shutil.which(command[0])
            if not executable:
                continue
            try:
                result = subprocess.run([executable, *command[1:]], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return PlatformResult(True, "Sessão bloqueada.", {"backend": command[0]})
                errors.append((result.stderr or result.stdout).strip())
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(str(exc))
        detail = "; ".join(filter(None, errors)) or "loginctl/xdg-screensaver não encontrados"
        return PlatformResult(False, f"Não consegui bloquear a sessão: {detail}")

    def launch_terminal(self, command: str | None = None) -> PlatformResult:
        shell = os.environ.get("SHELL") or "/bin/bash"
        if command:
            return self._spawn([shell, "-lc", command], "Comando iniciado no shell.")
        for terminal in ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal"):
            if shutil.which(terminal):
                return self._spawn([terminal], "Abrindo terminal.")
        return PlatformResult(False, "Nenhum emulador de terminal conhecido foi encontrado.")
