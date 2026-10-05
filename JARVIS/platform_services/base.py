"""Contrato comum para operações dependentes do sistema operacional."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


@dataclass
class PlatformResult:
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class PlatformServices(ABC):
    name = "unknown"

    @abstractmethod
    def open_application(self, command: str | Sequence[str], display_name: str = "aplicativo") -> PlatformResult:
        raise NotImplementedError

    @abstractmethod
    def open_path(self, path: str | Path) -> PlatformResult:
        raise NotImplementedError

    @abstractmethod
    def open_url(self, url: str) -> PlatformResult:
        raise NotImplementedError

    @abstractmethod
    def set_volume(self, level: int) -> PlatformResult:
        raise NotImplementedError

    @abstractmethod
    def get_volume(self) -> PlatformResult:
        raise NotImplementedError

    @abstractmethod
    def mute_volume(self) -> PlatformResult:
        raise NotImplementedError

    @abstractmethod
    def lock_session(self) -> PlatformResult:
        raise NotImplementedError

    @abstractmethod
    def launch_terminal(self, command: str | None = None) -> PlatformResult:
        raise NotImplementedError

    def process_info(self) -> PlatformResult:
        try:
            import psutil

            process = psutil.Process()
            return PlatformResult(True, "Informações do processo obtidas.", {
                "pid": process.pid,
                "name": process.name(),
                "status": process.status(),
            })
        except Exception as exc:
            return PlatformResult(False, f"Não consegui consultar o processo: {exc}")
