"""Implementação Windows; imports exclusivos ficam dentro dos métodos."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Sequence

from platform_services.base import PlatformResult, PlatformServices


class WindowsServices(PlatformServices):
    name = "windows"

    def open_application(self, command: str | Sequence[str], display_name: str = "aplicativo") -> PlatformResult:
        if isinstance(command, str):
            argv = [command] if "\\" in command or Path(command).suffix.lower() in {".exe", ".bat", ".cmd"} else shlex.split(command, posix=False)
        else:
            argv = list(command)
        if not argv:
            return PlatformResult(False, "Comando de aplicativo vazio.")
        try:
            if len(argv) == 1:
                os.startfile(argv[0])  # type: ignore[attr-defined]
            else:
                subprocess.Popen(argv)
            return PlatformResult(True, f"Abrindo {display_name}.")
        except OSError as exc:
            return PlatformResult(False, f"Não consegui abrir '{display_name}': {exc}")

    def open_path(self, path: str | Path) -> PlatformResult:
        target = Path(path).expanduser()
        if not target.exists():
            return PlatformResult(False, f"O caminho não existe: {target}")
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
            return PlatformResult(True, f"Abrindo {target}.")
        except OSError as exc:
            return PlatformResult(False, f"Não consegui abrir o caminho: {exc}")

    def open_url(self, url: str) -> PlatformResult:
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return PlatformResult(True, "Abrindo o endereço no navegador.")
        except OSError as exc:
            return PlatformResult(False, f"Não consegui abrir o endereço: {exc}")

    @staticmethod
    def _endpoint():
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        interface = AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    def set_volume(self, level: int) -> PlatformResult:
        level = max(0, min(100, int(level)))
        try:
            self._endpoint().SetMasterVolumeLevelScalar(level / 100, None)
            return PlatformResult(True, f"Volume ajustado para {level}%.", {"level": level, "backend": "pycaw"})
        except Exception as exc:
            return PlatformResult(False, f"Não consegui ajustar o volume com pycaw: {exc}")

    def get_volume(self) -> PlatformResult:
        try:
            level = round(self._endpoint().GetMasterVolumeLevelScalar() * 100)
            return PlatformResult(True, f"Volume em {level}%.", {"level": level, "backend": "pycaw"})
        except Exception as exc:
            return PlatformResult(False, f"Não consegui consultar o volume com pycaw: {exc}")

    def mute_volume(self) -> PlatformResult:
        try:
            self._endpoint().SetMute(1, None)
            return PlatformResult(True, "Áudio mutado.", {"backend": "pycaw"})
        except Exception as exc:
            return PlatformResult(False, f"Não consegui mutar o áudio com pycaw: {exc}")

    def lock_session(self) -> PlatformResult:
        try:
            import ctypes

            ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
            return PlatformResult(True, "Computador bloqueado.")
        except Exception as exc:
            return PlatformResult(False, f"Não consegui bloquear o computador: {exc}")

    def launch_terminal(self, command: str | None = None) -> PlatformResult:
        argv = [os.environ.get("COMSPEC", "cmd.exe")]
        if command:
            argv.extend(["/c", command])
        try:
            subprocess.Popen(argv)
            return PlatformResult(True, "Abrindo terminal.")
        except OSError as exc:
            return PlatformResult(False, f"Não consegui abrir o terminal: {exc}")
