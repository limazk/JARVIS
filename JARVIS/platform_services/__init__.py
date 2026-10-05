"""Seleção runtime da implementação do sistema operacional."""
from __future__ import annotations

import platform

from platform_services.base import PlatformServices


def get_platform_services(system_name: str | None = None) -> PlatformServices:
    detected = (system_name or platform.system()).lower()
    if detected == "windows":
        from platform_services.windows import WindowsServices

        return WindowsServices()
    if detected == "linux":
        from platform_services.linux import LinuxServices

        return LinuxServices()
    raise RuntimeError(f"Sistema operacional não suportado: {detected}")


__all__ = ["get_platform_services", "PlatformServices"]
