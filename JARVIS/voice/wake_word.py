"""
Wake word — detecção contínua do JARVIS.

Dois motores são suportados:

1) openWakeWord: 100% local e muito leve, ideal quando o modelo acústico
   corresponde exatamente à frase desejada. O modelo pronto "hey_jarvis"
   foi treinado para "Hey Jarvis", não para a palavra isolada "Jarvis".

2) STT: captura uma frase e procura WAKE_WORD na transcrição. No modo
   WAKE_WORD_ENGINE=auto ele é escolhido quando, por exemplo,
   WAKE_WORD=jarvis e WAKE_WORD_MODEL=hey_jarvis. O texto depois da wake
   word é reaproveitado como comando, então:
       "Jarvis, quanto ganhei essa semana?"
   vira uma única interação e não perde o começo da pergunta.

WAKE_WORD_ENGINE:
    auto          -> openWakeWord só quando o modelo corresponde à wake word;
                     caso contrário usa STT.
    openwakeword  -> força openWakeWord (fallback para STT se indisponível).
    stt           -> força detecção por STT.

Observação de privacidade: se STT_PROVIDER=google, o modo STT envia as
frases captadas ao serviço de reconhecimento. Para ficar 100% local sem
um modelo acústico customizado, use STT_PROVIDER=whisper. Para máxima
eficiência, forneça um modelo openWakeWord treinado especificamente para
"Jarvis".
"""
from __future__ import annotations

import inspect
import logging
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from config.settings import settings
from voice.listener import listener
from voice.microphone import microphone_coordinator

logger = logging.getLogger("jarvis.voice.wakeword")

_THRESHOLD = 0.5
_COOLDOWN_SECONDS = 2.0

WakeCallback = Callable[..., None]


def _normalize_phrase(value: str) -> str:
    value = value.replace("_", " ").replace("-", " ")
    return " ".join(value.lower().split())


def _model_matches_requested_wake_word(model: str, wake_word: str) -> bool:
    model_path = Path(model).expanduser()
    if model_path.is_file():
        # Modelo customizado: não dá para inferir a frase treinada pelo nome
        # do arquivo, então confiamos na configuração do usuário.
        return True
    return _normalize_phrase(model) == _normalize_phrase(wake_word)


def _extract_command_after_wake(text: str, wake_word: str) -> tuple[bool, Optional[str]]:
    """Retorna (wake_encontrada, comando_restante).

    Exemplos:
        "jarvis" -> (True, None)
        "jarvis quanto ganhei essa semana" ->
            (True, "quanto ganhei essa semana")
        "hey jarvis, abre o spotify" -> (True, "abre o spotify")
    """
    phrase = (wake_word or "").strip()
    if not text or not phrase:
        return False, None

    escaped = r"\s+".join(re.escape(part) for part in phrase.split())
    match = re.search(
        rf"(?<!\w){escaped}(?!\w)(?P<tail>.*)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return False, None

    tail = re.sub(
        r"^[\s,.:;!?\-–—]+",
        "",
        match.group("tail") or "",
    ).strip()
    return True, tail or None


class WakeWordDetector:
    def __init__(self, on_wake: WakeCallback) -> None:
        self.on_wake = on_wake
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return

        self._stop_event.clear()
        engine = (settings.wake_word_engine or "auto").strip().lower()
        if engine not in {"auto", "openwakeword", "stt"}:
            logger.warning(
                "WAKE_WORD_ENGINE=%r inválido; usando 'auto'.",
                engine,
            )
            engine = "auto"

        openwakeword_available = self._openwakeword_available()

        if engine == "stt":
            selected = "stt"
        elif engine == "openwakeword":
            selected = "openwakeword" if openwakeword_available else "stt"
        else:
            selected = (
                "openwakeword"
                if openwakeword_available
                and _model_matches_requested_wake_word(
                    settings.wake_word_model,
                    settings.wake_word,
                )
                else "stt"
            )
            if openwakeword_available and selected == "stt":
                logger.info(
                    "WAKE_WORD=%r não corresponde ao modelo openWakeWord=%r; "
                    "usando STT para reconhecer a palavra isolada.",
                    settings.wake_word,
                    settings.wake_word_model,
                )

        target = (
            self._run_openwakeword
            if selected == "openwakeword"
            else self._run_fallback
        )
        self._thread = threading.Thread(
            target=target,
            daemon=True,
            name="jarvis-wakeword",
        )
        self._thread.start()

        logger.info(
            "Detecção de wake word ('%s') iniciada via %s.",
            settings.wake_word,
            "openWakeWord" if selected == "openwakeword" else "STT",
        )

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = 5.0) -> None:
        if (
            self._thread is not None
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=timeout)

    def _dispatch_wake(self, command: Optional[str]) -> None:
        """Entrega o comando ao callback novo sem quebrar callbacks legados.

        Callbacks atuais podem aceitar um argumento opcional contendo o texto
        que veio depois de "Jarvis". Testes/código legado que ainda usam
        callback sem argumentos continuam funcionando.
        """
        try:
            inspect.signature(self.on_wake).bind(command)
        except (TypeError, ValueError):
            self.on_wake()
        else:
            self.on_wake(command)

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
            logger.warning(
                "Dependência do openWakeWord faltando (%s) — usando STT.",
                exc,
            )
            self._run_fallback()
            return

        try:
            configured_model = settings.wake_word_model
            custom_path = Path(configured_model).expanduser()
            model_ref = (
                str(custom_path.resolve())
                if custom_path.is_file()
                else configured_model
            )
            if not custom_path.is_file():
                openwakeword.utils.download_models([configured_model])

            model = Model(wakeword_models=[model_ref])
            model_name = (
                Path(model_ref).stem
                if custom_path.is_file()
                else configured_model
            )
        except Exception as exc:
            logger.error(
                "Não consegui carregar o modelo openWakeWord (%s) — usando STT.",
                exc,
            )
            self._run_fallback()
            return

        chunk = 1280  # 80ms a 16kHz
        cooldown_until = 0.0

        while not self._stop_event.is_set():
            if not microphone_coordinator.acquire(blocking=False):
                self._stop_event.wait(0.1)
                continue

            audio = pyaudio.PyAudio()
            stream = None
            detected = False
            fallback = False

            try:
                stream = audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=chunk,
                )

                while not self._stop_event.is_set():
                    pcm = stream.read(
                        chunk,
                        exception_on_overflow=False,
                    )
                    frame = np.frombuffer(pcm, dtype=np.int16)
                    prediction = model.predict(frame)
                    score = prediction.get(model_name, 0.0)
                    now = time.monotonic()

                    if (
                        score >= _THRESHOLD
                        and now >= cooldown_until
                    ):
                        logger.debug(
                            "Wake word detectada (score=%.2f).",
                            score,
                        )
                        cooldown_until = now + _COOLDOWN_SECONDS
                        detected = True
                        break
            except Exception as exc:
                logger.error(
                    "Falha no stream openWakeWord (%s).",
                    exc,
                )
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
                self._dispatch_wake(None)

    def _run_fallback(self) -> None:
        wake_word = settings.wake_word.strip()
        phrase_limit = max(
            3.0,
            float(settings.wake_command_phrase_time_limit),
        )

        while not self._stop_event.is_set():
            text = listener.listen_once(
                phrase_time_limit=phrase_limit,
            )
            matched, command = _extract_command_after_wake(
                text or "",
                wake_word,
            )

            if matched:
                logger.debug(
                    "Wake word detectada por STT%s.",
                    " com comando na mesma frase"
                    if command
                    else "",
                )
                # Síncrono de propósito: só volta a escutar depois que o
                # comando atual terminar, evitando disputa pelo microfone.
                self._dispatch_wake(command)
            elif text is None:
                # Evita loop apertado se o microfone estiver indisponível.
                time.sleep(0.5)
