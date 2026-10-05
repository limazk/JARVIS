"""Coordenação única do dispositivo de captura de áudio."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


class MicrophoneCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def acquire(self, blocking: bool = False) -> bool:
        return self._lock.acquire(blocking=blocking)

    def release(self) -> None:
        self._lock.release()

    @contextmanager
    def claim(self, blocking: bool = False) -> Iterator[bool]:
        acquired = self.acquire(blocking=blocking)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


microphone_coordinator = MicrophoneCoordinator()
