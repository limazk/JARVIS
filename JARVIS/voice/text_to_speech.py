"""
Text-to-Speech modular — seção 6 do spec.

Mesma ideia do core/brain.py: uma interface comum (TTSProvider) com
implementações trocáveis via TTS_PROVIDER no .env.

    piper       -> neural pt-BR Faber offline (padrão, após setup)
    edge        -> Edge TTS (Microsoft, serviço não-oficial)
    espeak      -> 100% offline no Linux (espeak-ng/espeak via WAV reproduzido no pygame)
    pyttsx3     -> fallback legado, qualidade robótica, pode falhar em Python recente
    elevenlabs  -> pago, melhor qualidade (precisa de ELEVENLABS_API_KEY)

As implementações que geram arquivo (edge/elevenlabs) devolvem o
caminho; quem toca é sempre o audio_player (para permitir
interrupção, seção 7). O pyttsx3 fala direto pela biblioteca do
sistema e não passa pelo audio_player — limitação documentada:
"Jarvis, para" não interrompe uma fala em pyttsx3 (só nos outros
dois provedores).
"""
from __future__ import annotations

import atexit
import logging
import os
import platform
import shutil
import subprocess
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


class PiperTTSProvider(TTSProvider):
    """Interface do sintetizador Piper isolado da versão do Python."""

    def synthesize(self, text: str) -> Optional[Path]:
        from voice.piper_engine import synthesize_piper
        return synthesize_piper(text)


class EspeakProvider(TTSProvider):
    """Gera WAV offline no Linux; evita callback frágil do pyttsx3/espeak.

    Usa --stdin para que o texto seja dado, nunca interpretado como argumento
    de shell. A reprodução continua pelo AudioPlayer, permitindo interrupção.
    """

    def synthesize(self, text: str) -> Optional[Path]:
        if platform.system() != "Linux":
            return None
        executable = shutil.which("espeak-ng") or shutil.which("espeak")
        if not executable:
            logger.info("espeak-ng/espeak indisponível: sudo apt install espeak-ng")
            return None
        fd, name = tempfile.mkstemp(prefix="jarvis_espeak_", suffix=".wav")
        path = Path(name)
        try:
            with os.fdopen(fd, "wb") as output:
                proc = subprocess.run(
                    [executable, "-v", "pt-br", "-s", "165", "--stdout", "--stdin"],
                    input=text.encode("utf-8"),
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    check=False,
                )
            if proc.returncode != 0 or path.stat().st_size < 44:
                logger.warning(
                    "Falha ao gerar WAV com eSpeak (código %s): %s",
                    proc.returncode, proc.stderr.decode("utf-8", "replace")[:200],
                )
                path.unlink(missing_ok=True)
                return None
            # A reprodução pode ser não bloqueante; mantenha o arquivo até
            # encerrar o processo para não interromper o pygame.
            atexit.register(path.unlink, missing_ok=True)
            return path
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("eSpeak local indisponível (%s).", exc)
            path.unlink(missing_ok=True)
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
    providers = {"piper": PiperTTSProvider, "edge": EdgeTTSProvider, "espeak": EspeakProvider, "pyttsx3": Pyttsx3Provider, "elevenlabs": ElevenLabsProvider}
    provider_cls = providers.get(settings.tts_provider, EdgeTTSProvider)
    return provider_cls()


def speak(text: str, blocking: bool = True) -> None:
    """Fala com modelo Piper offline e fallback seguro.

    Ordem:
        piper      -> eSpeak -> pyttsx3
        edge       -> Piper -> eSpeak -> pyttsx3
        elevenlabs -> Piper -> Edge -> eSpeak -> pyttsx3
        espeak     -> pyttsx3
        pyttsx3    -> direto

    Piper não gasta tokens/API nem baixa arquivos automaticamente. Instale
    o modelo pt-BR com scripts/setup_piper_voice.py para obter voz neural.
    """
    from voice.audio_player import player
    from voice.formatting import prepare_speech

    text = prepare_speech(text)
    if not text:
        return

    primary = get_tts_provider()
    if isinstance(primary, PiperTTSProvider):
        sequence = [primary, EspeakProvider(), Pyttsx3Provider()]
    elif isinstance(primary, ElevenLabsProvider):
        sequence = [
            primary, PiperTTSProvider(), EdgeTTSProvider(),
            EspeakProvider(), Pyttsx3Provider(),
        ]
    elif isinstance(primary, EdgeTTSProvider):
        sequence = [primary, PiperTTSProvider(), EspeakProvider(), Pyttsx3Provider()]
    elif isinstance(primary, EspeakProvider):
        sequence = [primary, Pyttsx3Provider()]
    else:
        sequence = [primary]

    for provider in sequence:
        try:
            audio_path = provider.synthesize(text)
        except Exception:
            # Nunca interromper a interação inteira por um provedor de TTS.
            logger.exception("Erro ao sintetizar com %s.", type(provider).__name__)
            continue

        if audio_path is None:
            # pyttsx3 fala diretamente, sem um arquivo para reproduzir.
            if isinstance(provider, Pyttsx3Provider):
                return
            continue

        trace = current_trace()
        if trace is not None:
            trace.mark_elapsed("tts_start_duration")
        try:
            player.play(str(audio_path), blocking=blocking)
        except Exception:
            logger.exception("Falha na reprodução da voz gerada por %s.", type(provider).__name__)
            continue
        return

    logger.warning("Nenhum sintetizador de voz disponível para reproduzir a resposta.")
