"""
Text-to-Speech modular — seção 6 do spec.

Mesma ideia do core/brain.py: uma interface comum (TTSProvider) com
implementações trocáveis via TTS_PROVIDER no .env.

    edge        -> Edge TTS (Microsoft, grátis, vozes neurais pt-BR) [padrão]
    pyttsx3     -> 100% offline, qualidade robótica, sempre funciona
    elevenlabs  -> pago, melhor qualidade (precisa de ELEVENLABS_API_KEY)

As implementações que geram arquivo (edge/elevenlabs) devolvem o
caminho; quem toca é sempre o audio_player (para permitir
interrupção, seção 7). O pyttsx3 fala direto pela biblioteca do
sistema e não passa pelo audio_player — limitação documentada:
"Jarvis, para" não interrompe uma fala em pyttsx3 (só nos outros
dois provedores).
"""
from __future__ import annotations

import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from config.settings import settings
from core.performance import current_trace

logger = logging.getLogger("jarvis.voice.tts")


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> Optional[Path]:
        """Gera um arquivo de áudio com o texto falado e devolve o caminho (ou None)."""
        raise NotImplementedError


class EdgeTTSProvider(TTSProvider):
    def synthesize(self, text: str) -> Optional[Path]:
        try:
            import asyncio

            import edge_tts
        except ImportError:
            logger.warning("edge-tts não instalado (pip install edge-tts).")
            return None

        out_path = Path(tempfile.gettempdir()) / "jarvis_tts_output.mp3"

        async def _gen() -> None:
            communicate = edge_tts.Communicate(text, settings.edge_tts_voice)
            await communicate.save(str(out_path))

        try:
            asyncio.run(_gen())
            return out_path
        except Exception as exc:
            logger.error("Falha no Edge TTS: %s", exc)
            return None


class Pyttsx3Provider(TTSProvider):
    def synthesize(self, text: str) -> Optional[Path]:
        try:
            import pyttsx3
        except ImportError:
            logger.warning("pyttsx3 não instalado (pip install pyttsx3).")
            return None
        try:
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            logger.error("Falha no pyttsx3: %s", exc)
        return None  # já falou direto; não há arquivo para o audio_player tocar


class ElevenLabsProvider(TTSProvider):
    def synthesize(self, text: str) -> Optional[Path]:
        if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
            logger.warning("ElevenLabs não configurado (ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID no .env).")
            return None
        try:
            import requests

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
            headers = {"xi-api-key": settings.elevenlabs_api_key, "Content-Type": "application/json"}
            payload = {"text": text, "model_id": "eleven_multilingual_v2"}
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()

            out_path = Path(tempfile.gettempdir()) / "jarvis_tts_output.mp3"
            out_path.write_bytes(resp.content)
            return out_path
        except Exception as exc:
            logger.error("Falha no ElevenLabs: %s", exc)
            return None


def get_tts_provider() -> TTSProvider:
    providers = {"edge": EdgeTTSProvider, "pyttsx3": Pyttsx3Provider, "elevenlabs": ElevenLabsProvider}
    provider_cls = providers.get(settings.tts_provider, EdgeTTSProvider)
    return provider_cls()


def speak(text: str, blocking: bool = True) -> None:
    """
    Sintetiza e toca a fala. Se o provedor configurado falhar, tenta os
    próximos da cadeia de fallback: (ElevenLabs, se era o configurado) ->
    Edge TTS (grátis) -> pyttsx3 (100% offline, não depende de rede nem de
    nenhum serviço externo — por isso é sempre o último da cadeia e nunca
    falha silenciosamente). O Edge TTS é uma API não-oficial que a Microsoft
    quebra de vez em quando (erro "403 Invalid response status" — nesse caso,
    atualize o pacote com `pip install -U edge-tts`) — quando ele mesmo é o
    provedor configurado e falha, pula direto pro pyttsx3 em vez de tentar o
    Edge de novo.
    """
    from voice.audio_player import player

    provider = get_tts_provider()
    audio_path = provider.synthesize(text)

    if audio_path is None and not isinstance(provider, Pyttsx3Provider):
        if not isinstance(provider, EdgeTTSProvider):
            logger.info("Provedor de TTS configurado falhou; tentando fallback Edge TTS.")
            audio_path = EdgeTTSProvider().synthesize(text)

        if audio_path is None:
            logger.info("Edge TTS indisponível; tentando fallback pyttsx3 (100%% offline).")
            trace = current_trace()
            if trace is not None:
                trace.mark_elapsed("tts_start_duration")
            Pyttsx3Provider().synthesize(text)
            return

    if audio_path is not None:
        trace = current_trace()
        if trace is not None:
            trace.mark_elapsed("tts_start_duration")
        player.play(str(audio_path), blocking=blocking)
