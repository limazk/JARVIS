"""
Speech-to-Text modular — seção 6 do spec.

    google    -> speech_recognition + Google Web Speech API (grátis, sem key, online) [padrão]
    whisper   -> faster-whisper local (mais pesado — baixa um modelo na 1ª vez —
                 porém 100% offline)

Recebe sempre um objeto AudioData do `speech_recognition`, já
capturado localmente pelo microfone (voice/listener.py). O áudio só
sai da máquina se STT_PROVIDER=google.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from config.settings import settings

logger = logging.getLogger("jarvis.voice.stt")


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_data) -> Optional[str]:
        raise NotImplementedError


class GoogleSTTProvider(STTProvider):
    def transcribe(self, audio_data) -> Optional[str]:
        try:
            import speech_recognition as sr
        except ImportError:
            logger.warning("SpeechRecognition não instalado (pip install SpeechRecognition).")
            return None
        try:
            recognizer = sr.Recognizer()
            return recognizer.recognize_google(audio_data, language=settings.language)
        except sr.UnknownValueError:
            return None
        except Exception as exc:
            logger.debug("Google STT falhou (%s).", exc)
            return None


class WhisperSTTProvider(STTProvider):
    """
    100% local. Requer `faster-whisper` (pip install faster-whisper) — pacote
    pesado que baixa um modelo na primeira execução, por isso é opcional e
    carregado sob demanda (lazy), não no import do módulo.
    """

    _model = None

    def _get_model(self):
        if WhisperSTTProvider._model is None:
            from faster_whisper import WhisperModel

            WhisperSTTProvider._model = WhisperModel("small", device="cpu", compute_type="int8")
        return WhisperSTTProvider._model

    def transcribe(self, audio_data) -> Optional[str]:
        try:
            model = self._get_model()
        except ImportError:
            logger.warning("faster-whisper não instalado (pip install faster-whisper).")
            return None
        except Exception as exc:
            logger.error("Falha ao carregar o modelo Whisper local: %s", exc)
            return None

        import io

        try:
            wav_bytes = audio_data.get_wav_data()
            segments, _ = model.transcribe(io.BytesIO(wav_bytes), language="pt")
            text = " ".join(segment.text for segment in segments).strip()
            return text or None
        except Exception as exc:
            logger.error("Falha na transcrição Whisper: %s", exc)
            return None


def get_stt_provider() -> STTProvider:
    providers = {"google": GoogleSTTProvider, "whisper": WhisperSTTProvider}
    provider_cls = providers.get(settings.stt_provider, GoogleSTTProvider)
    return provider_cls()
