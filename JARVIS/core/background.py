"""Runtime headless para systemd --user e execução manual."""
from __future__ import annotations

import logging
import signal
import threading
from typing import Callable

from config.settings import settings
from core.agent import JarvisAgent
from core.performance import PerformanceTrace, request_trace
from integrations.rotina import RotinaError
from jarvis_rotina import RotinaProcessManager
from voice.listener import listener
from voice.text_to_speech import speak
from voice.wake_word import WakeWordDetector

logger = logging.getLogger("jarvis.background")


class BackgroundRuntime:
    def __init__(self, stop_event: threading.Event | None = None,
                 detector_factory: Callable[..., WakeWordDetector] = WakeWordDetector) -> None:
        self.stop_event = stop_event or threading.Event()
        self.detector_factory = detector_factory
        self.agent: JarvisAgent | None = None
        self.detector: WakeWordDetector | None = None
        self.rotina = RotinaProcessManager()
        self._handling = threading.Lock()

    @staticmethod
    def _confirm_unavailable(_: str) -> bool:
        return False

    def _speak(self, text: str) -> None:
        logger.info("JARVIS: %s", text)
        if settings.voice_enabled:
            speak(text, blocking=True)

    def _on_wake(self, prefilled_command: str | None = None) -> None:
        if not self._handling.acquire(blocking=False):
            return
        trace = PerformanceTrace()
        try:
            with request_trace(trace):
                threading.Thread(
                    target=self._prefetch_rotina_health,
                    daemon=True,
                    name="jarvis-rotina-prefetch",
                ).start()

                # No fallback por STT, "Jarvis, quanto ganhei essa semana?"
                # já chega aqui com o restante da frase em prefilled_command.
                # Processamos direto: não falamos por cima do usuário e não
                # abrimos o microfone uma segunda vez, evitando perder o começo.
                text = (prefilled_command or "").strip()

                if not text:
                    # Quando o usuário falou apenas "Jarvis", damos uma
                    # confirmação curta e só então capturamos o comando.
                    # "Sim?" termina bem mais rápido que "Estou ouvindo." e
                    # reduz a janela em que o começo da pergunta podia sumir.
                    self._speak(settings.wake_greeting.strip() or "Sim?")
                    trace.mark_elapsed("wake_to_stt")
                    text = listener.listen_once(
                        phrase_time_limit=settings.wake_command_phrase_time_limit
                    )

                if not text:
                    logger.info(
                        "Wake word detectada, mas nenhum comando foi transcrito."
                    )
                    return

                logger.info("Comando de voz transcrito; iniciando agente.")
                if self.agent is not None:
                    self._speak(
                        self.agent.process(text, response_mode="voice")
                    )
        finally:
            trace.log()
            self._handling.release()

    def _prefetch_rotina_health(self) -> None:
        """Aquece apenas a conexão/health local; não busca dados pessoais."""
        try:
            self.rotina.client.health()
        except RotinaError:
            pass

    def request_stop(self, *_: object) -> None:
        self.stop_event.set()

    def run(self, install_signal_handlers: bool = True) -> None:
        logger.info("Iniciando JARVIS em background (sem interface gráfica).")
        self.rotina.ensure_running()
        self.agent = JarvisAgent(confirm_callback=self._confirm_unavailable, on_reminder_due=self._speak)
        if install_signal_handlers and threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self.request_stop)
            signal.signal(signal.SIGINT, self.request_stop)
        try:
            if not listener.is_ready():
                logger.warning("Microfone indisponível na inicialização; o detector continuará tentando.")
            if settings.wake_word_enabled:
                self.detector = self.detector_factory(on_wake=self._on_wake)
                self.detector.start()
                logger.info("Aguardando wake word '%s' (modelo '%s').", settings.wake_word, settings.wake_word_model)
            else:
                logger.warning("WAKE_WORD_ENABLED=false; serviço ativo sem captura contínua.")
            self.stop_event.wait()
        finally:
            if self.detector is not None:
                self.detector.stop()
                self.detector.join()
            if self.agent is not None:
                self.agent.shutdown()
            self.rotina.stop()
            logger.info("JARVIS background encerrado; recursos liberados.")
