"""
Player de áudio controlável — seção 7 do spec (interrupção da fala).

Usa `pygame.mixer`: diferente de tocar áudio com playsound ou
afins, dá para chamar stop() a qualquer momento e a reprodução para
imediatamente. É isso que permite implementar "Jarvis, para".

Existe uma única instância compartilhada (`player`) porque o Jarvis
só fala uma coisa de cada vez — iniciar uma nova reprodução
naturalmente substitui a anterior.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger("jarvis.voice.player")


class AudioPlayer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._initialized = False

    def _ensure_init(self) -> bool:
        if self._initialized:
            return True
        try:
            import pygame

            pygame.mixer.init()
            self._initialized = True
            return True
        except Exception as exc:
            logger.warning("Não foi possível iniciar o player de áudio (%s). Voz de saída desabilitada.", exc)
            return False

    def play(self, file_path: str, blocking: bool = True) -> None:
        if not self._ensure_init():
            return
        import time

        import pygame

        with self._lock:
            # No Windows, pygame.mixer.music.load() mantém o arquivo aberto
            # (travado) até que outro arquivo seja carregado OU unload() seja
            # chamado — diferente do Linux/Mac, o Windows não deixa outro
            # processo (aqui, o próprio edge-tts na próxima fala) sobrescrever
            # um arquivo ainda aberto, e isso quebrava com "PermissionError:
            # [Errno 13] Permission denied" no arquivo temporário do TTS toda
            # vez que o Jarvis tentava falar de novo. unload() antes de
            # carregar o próximo áudio libera o arquivo anterior.
            self._unload_safely()
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()

        if blocking:
            while self.is_playing():
                time.sleep(0.1)
            with self._lock:
                self._unload_safely()

    def stop(self) -> None:
        if not self._initialized:
            return
        import pygame

        with self._lock:
            pygame.mixer.music.stop()
            self._unload_safely()

    def _unload_safely(self) -> None:
        """Libera o arquivo de áudio atualmente carregado, se houver.

        `unload()` só existe a partir do pygame-ce 2.1.4+ — protegido por
        try/except também para não quebrar caso alguém volte a usar o
        pygame original (sem esse método) por qualquer motivo.
        """
        import pygame

        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

    def is_playing(self) -> bool:
        if not self._initialized:
            return False
        import pygame

        return bool(pygame.mixer.music.get_busy())


# Instância única compartilhada por todo o Jarvis.
player = AudioPlayer()
