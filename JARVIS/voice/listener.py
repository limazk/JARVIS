"""
Captura de microfone — seção 6 do spec.

Usa `speech_recognition`, que já faz detecção de silêncio
localmente (a gravação só termina quando a pessoa para de falar, ou
no limite de tempo) — nenhum áudio sai da máquina até que um
STTProvider explicitamente processe o clipe (voice/speech_to_text.py).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from config.settings import settings
from voice.speech_to_text import get_stt_provider
from voice.microphone import microphone_coordinator
from core.performance import current_trace

logger = logging.getLogger("jarvis.voice.listener")


@dataclass
class ListenOutcome:
    """
    Resultado detalhado de uma captura (ver `listen_once_detailed` abaixo).

    Existe porque `listen_once()` sempre devolveu só `str | None` — e um
    `None` podia significar quatro coisas bem diferentes (microfone
    indisponível, ninguém falou nada, falou mas o STT não entendeu, ou um
    erro de verdade), mas quem chamava não tinha como saber qual. Na
    prática isso fazia o Jarvis "falhar em silêncio": a pessoa falava,
    nada acontecia na tela, e parecia que o microfone simplesmente não
    reconhecia nada — quando às vezes era só o reconhecimento de voz não
    tendo entendido o áudio. `reason` deixa quem chama (interface/app.py,
    interface_web/bridge.py) dar um feedback honesto e específico em vez
    de ficar quieto.
    """

    text: Optional[str]
    reason: str  # "ok" | "no_speech" | "not_understood" | "mic_busy" | "mic_unavailable" | "error"
    detail: str = ""


# Mensagens prontas em pt-BR por motivo — usadas por interface/app.py e
# interface_web/bridge.py pra avisar o usuário de verdade em vez de ficar
# quieto quando `listen_once`/`listen_once_detailed` não traz texto. "ok" e
# "mic_busy" não têm mensagem: "ok" segue o fluxo normal (processa o texto) e
# "mic_busy" é uma disputa interna rara entre duas capturas ao mesmo tempo,
# não um problema que o usuário precise saber.
_FEEDBACK_BY_REASON = {
    "no_speech": (
        "Não ouvi nada. Pode ser o microfone errado selecionado no Windows, o volume de "
        "entrada baixo demais, ou você começou a falar um pouco antes/depois da hora — "
        "tente falar logo em seguida, bem perto do microfone."
    ),
    "not_understood": (
        "Ouvi um áudio, mas não consegui entender o que foi dito. Pode repetir, falando "
        "um pouco mais devagar e perto do microfone?"
    ),
    "mic_unavailable": "Não consegui acessar um microfone neste computador.",
    "error": "Deu um erro ao captar o áudio do microfone: {detail}",
}


def feedback_message(outcome: "ListenOutcome") -> Optional[str]:
    """Mensagem em pt-BR pra mostrar ao usuário quando a captura não deu texto, ou None se não houver nada a dizer."""
    template = _FEEDBACK_BY_REASON.get(outcome.reason)
    if template is None:
        return None
    return template.format(detail=outcome.detail)

# Depois de uma falha ao inicializar o microfone, espera esse tempo antes de
# tentar de novo (em vez de nunca mais tentar) — evita duas coisas ao mesmo
# tempo: martelar o dispositivo em loops apertados quando o mic realmente não
# existe, e travar "sem microfone" pelo resto da execução por causa de uma
# falha só passageira (ex.: o driver de áudio do Windows ainda inicializando
# bem na hora em que o Jarvis abre sozinho com o computador).
_RETRY_COOLDOWN_SECONDS = 15.0


class MicrophoneListener:
    def __init__(self) -> None:
        self._recognizer = None
        self._microphone = None
        self._retry_after = 0.0  # timestamp (time.monotonic); 0 = nunca falhou ainda
        # Protege contra dois pontos do Jarvis tentando usar o microfone ao
        # mesmo tempo (ex.: a detecção de wake word em segundo plano E o
        # botão de microfone manual da interface, se clicado nesse meio
        # tempo) — sem isso, a segunda chamada quebra com "This audio
        # source is already inside a context manager" (erro real visto em
        # produção), porque a biblioteca speech_recognition não permite dois
        # `with microphone:` abertos ao mesmo tempo no mesmo dispositivo.

    def is_ready(self) -> bool:
        """Checa a disponibilidade do microfone (com um pequeno cooldown entre tentativas)."""
        return self._ensure_ready()

    def _ensure_ready(self) -> bool:
        if self._recognizer is not None:
            return True
        if time.monotonic() < self._retry_after:
            return False
        if not microphone_coordinator.acquire(blocking=False):
            return False
        try:
            import speech_recognition as sr

            self._recognizer = sr.Recognizer()
            # Ajusta o detector de fim de fala para português natural.
            # O padrão da biblioteca (pause_threshold ~0.8s) é agressivo
            # para frases com pequenas pausas e podia cortar perguntas como
            # "quanto ganhei ... essa semana".
            pause_threshold = max(0.3, float(settings.stt_pause_threshold))
            self._recognizer.pause_threshold = pause_threshold
            self._recognizer.phrase_threshold = max(
                0.1, float(settings.stt_phrase_threshold)
            )
            self._recognizer.non_speaking_duration = min(
                pause_threshold,
                max(0.1, float(settings.stt_non_speaking_duration)),
            )
            self._microphone = sr.Microphone()
            with self._microphone as source:
                # 1s em vez dos 0.5s originais — meio segundo é pouco tempo
                # pra calibrar o limiar de energia (o que decide "isso é
                # fala" vs "isso é silêncio/ruído de fundo") direito; se
                # pegar um pico de ruído nesse instante (ventoinha, por
                # exemplo), o limiar fica alto demais e fala normal depois
                # passa a ser ignorada como se fosse silêncio — um dos jeitos
                # do microfone "parecer que não reconhece" sem erro nenhum.
                self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
            return True
        except Exception as exc:
            logger.error("Não consegui inicializar o microfone (%s). Voz de entrada desabilitada por agora.", exc)
            self._recognizer = None
            self._microphone = None
            self._retry_after = time.monotonic() + _RETRY_COOLDOWN_SECONDS
            return False
        finally:
            microphone_coordinator.release()

    def listen_once(self, phrase_time_limit: Optional[float] = None) -> Optional[str]:
        """
        Grava até detectar silêncio (ou o limite) e devolve o texto transcrito
        (ou None, por qualquer motivo). Mantido por compatibilidade com quem só
        precisa do texto — pra dar um retorno honesto ao usuário sobre O QUE
        deu errado quando não deu certo, use `listen_once_detailed()`.
        """
        return self.listen_once_detailed(phrase_time_limit).text

    def listen_once_detailed(self, phrase_time_limit: Optional[float] = None) -> ListenOutcome:
        """
        Igual a `listen_once`, mas devolve também o MOTIVO de não ter
        devolvido texto — essencial pra interface conseguir dizer pro
        usuário "não ouvi nada" (pode ser mic errado/baixo demais) vs "ouvi
        mas não entendi" (sotaque, ruído, idioma do STT) vs "deu erro de
        verdade", em vez de ficar em silêncio nos três casos.
        """
        stt_started = time.perf_counter()
        if not self._ensure_ready():
            return ListenOutcome(text=None, reason="mic_unavailable")

        # Não bloqueia esperando o microfone ficar livre — se outra captura já
        # está em andamento (ex.: a voz contínua acabou de ouvir "jarvis" e já
        # está gravando o comando), essa chamada simplesmente desiste com None
        # em vez de travar o quem chamou por até `phrase_time_limit` segundos
        # esperando, ou de quebrar com um erro de concorrência da lib.
        if not microphone_coordinator.acquire(blocking=False):
            logger.debug("Microfone já em uso por outra captura — ignorando esta chamada.")
            return ListenOutcome(text=None, reason="mic_busy")

        try:
            import speech_recognition as sr

            try:
                with self._microphone as source:
                    audio = self._recognizer.listen(
                        source,
                        timeout=float(settings.stt_listen_timeout),
                        phrase_time_limit=phrase_time_limit,
                    )
            except sr.WaitTimeoutError:
                return ListenOutcome(text=None, reason="no_speech")
            except Exception as exc:
                logger.error("Erro capturando áudio: %s", exc)
                return ListenOutcome(text=None, reason="error", detail=str(exc))
        finally:
            microphone_coordinator.release()

        text = get_stt_provider().transcribe(audio)
        trace = current_trace()
        if trace is not None:
            trace.set("stt_duration", time.perf_counter() - stt_started)
        if text:
            return ListenOutcome(text=text, reason="ok")
        return ListenOutcome(text=None, reason="not_understood")

    def listen_loop(self, on_text: Callable[[str], None], should_stop: Callable[[], bool]) -> None:
        """Loop bloqueante: chama on_text(texto) para cada frase entendida, até should_stop() ser True."""
        while not should_stop():
            text = self.listen_once(phrase_time_limit=8)
            if text:
                on_text(text)


# Instância única compartilhada (evita reabrir o microfone repetidamente).
listener = MicrophoneListener()
