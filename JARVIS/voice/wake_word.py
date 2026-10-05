"""
Wake word — seção 8 do spec ("Jarvis" sempre ouvindo, tipo Alexa).

Duas implementações, escolhidas automaticamente pelo que estiver
instalado:

1) openWakeWord (preferida): motor de wake word 100% local e leve,
   feito exatamente pra isso — analisa só o padrão acústico de
   janelas curtas de áudio (80ms) em busca da palavra, sem NUNCA
   transcrever nada nem mandar áudio pra fora, até detectar. Usa o
   modelo pronto `hey_jarvis` (já treinado pela própria biblioteca —
   não precisa treinar nada). Requer `pip install openwakeword`
   (baixa o modelo, ~1-2MB, na primeira execução).

2) Fallback simplificado (se openwakeword não estiver instalado): o
   microfone é monitorado continuamente por voice/listener.py — a
   detecção de "alguém está falando" é local (limiar de energia do
   `speech_recognition`), mas cada frase captada É transcrita via o
   STT_PROVIDER configurado só pra checar se contém a wake word.
   Funciona, mas se STT_PROVIDER=google isso manda pra nuvem trechos
   de fala mesmo sem a wake word ter sido dita — pra ficar 100% local
   nesse modo, use STT_PROVIDER=whisper.

Em qualquer um dos dois casos, o resto do Jarvis só conhece
`WakeWordDetector.start()`/`stop()` — trocar a implementação aqui não
afeta mais nada.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from config.settings import settings
from voice.listener import listener
from voice.microphone import microphone_coordinator

logger = logging.getLogger("jarvis.voice.wakeword")

_THRESHOLD = 0.5
_COOLDOWN_SECONDS = 2.0  # evita disparar várias vezes seguidas pra mesma chamada


class WakeWordDetector:
    def __init__(self, on_wake: Callable[[], None]) -> None:
        self.on_wake = on_wake
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        use_openwakeword = self._openwakeword_available()
        target = self._run_openwakeword if use_openwakeword else self._run_fallback
        self._thread = threading.Thread(target=target, daemon=True, name="jarvis-wakeword")
        self._thread.start()
        logger.info(
            "Detecção de wake word ('%s') iniciada via %s.",
            settings.wake_word,
            "openWakeWord" if use_openwakeword else "fallback por STT",
        )

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = 5.0) -> None:
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=timeout)

    @staticmethod
    def _openwakeword_available() -> bool:
        try:
            import openwakeword  # noqa: F401
        except ImportError:
            return False
        return True

    def _run_openwakeword(self) -> None:
        try:
            import numpy as np
            import openwakeword
            import pyaudio
            from openwakeword.model import Model
        except ImportError as exc:
            logger.warning("Dependência do openWakeWord faltando (%s) — usando fallback por STT.", exc)
            self._run_fallback()
            return

        try:
            configured_model = settings.wake_word_model
            custom_path = Path(configured_model).expanduser()
            model_ref = str(custom_path.resolve()) if custom_path.is_file() else configured_model
            if not custom_path.is_file():
                openwakeword.utils.download_models([configured_model])
            model = Model(wakeword_models=[model_ref])
            model_name = Path(model_ref).stem if custom_path.is_file() else configured_model
        except Exception as exc:
            logger.error("Não consegui carregar o modelo do openWakeWord (%s) — usando fallback por STT.", exc)
            self._run_fallback()
            return

        chunk = 1280  # 80ms a 16kHz — tamanho de janela recomendado pelo openWakeWord
        cooldown_until = 0.0
        while not self._stop_event.is_set():
            # O stream do wake word é fechado antes do callback. Assim o STT
            # consegue abrir o mesmo dispositivo sem concorrer com PyAudio.
            if not microphone_coordinator.acquire(blocking=False):
                self._stop_event.wait(0.1)
                continue
            audio = pyaudio.PyAudio()
            stream = None
            detected = False
            fallback = False
            try:
                stream = audio.open(format=pyaudio.paInt16, channels=1, rate=16000,
                                    input=True, frames_per_buffer=chunk)
                while not self._stop_event.is_set():
                    pcm = stream.read(chunk, exception_on_overflow=False)
                    frame = np.frombuffer(pcm, dtype=np.int16)
                    prediction = model.predict(frame)
                    score = prediction.get(model_name, 0.0)
                    now = time.monotonic()
                    if score >= _THRESHOLD and now >= cooldown_until:
                        logger.debug("Wake word detectada (score=%.2f).", score)
                        cooldown_until = now + _COOLDOWN_SECONDS
                        detected = True
                        break
            except Exception as exc:
                logger.error("Falha no stream openWakeWord (%s).", exc)
                if stream is None:
                    fallback = True
                else:
                    raise
            finally:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
                audio.terminate()
                microphone_coordinator.release()
            if fallback:
                self._run_fallback()
                return
            if detected and not self._stop_event.is_set():
                self.on_wake()

    def _run_fallback(self) -> None:
        wake_word = settings.wake_word.lower()
        while not self._stop_event.is_set():
            text = listener.listen_once(phrase_time_limit=3)
            if text and wake_word in text.lower():
                logger.debug("Wake word detectada em: %r", text)
                self.on_wake()  # síncrono de propósito — ver o comentário em
                # interface/app.py::_on_wake_triggered. Só volta a escutar
                # depois que on_wake() retornar de verdade.
            elif text is None:
                # Rede de segurança: se o microfone estiver com problema de
                # verdade (não só uma falha passageira), listener.listen_once
                # pode voltar quase instantaneamente por um tempo (durante o
                # cooldown de retry do voice/listener.py) — sem essa pequena
                # pausa, isso viraria um loop apertado gastando CPU à toa e
                # enchendo o log de erro repetido centenas de vezes por segundo.
                time.sleep(0.5)
