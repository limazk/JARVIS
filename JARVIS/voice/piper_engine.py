"""Piper TTS via executável local independente do Python do JARVIS.

Não instala pacotes nem baixa modelos durante uma resposta. Para configurar,
rode scripts/setup_piper_voice.py uma vez. Modelo e binário permanecem locais.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from config.settings import settings

logger = logging.getLogger("jarvis.voice.piper")

VOICE_NAME = "pt_BR-faber-medium"


def default_model_path() -> Path:
    return settings.base_dir / "voice" / "models" / f"{VOICE_NAME}.onnx"


def default_bin_path() -> Path:
    return settings.base_dir / "voice" / "piper_runtime" / "piper" / "piper"


def piper_model_path() -> Path:
    path = getattr(settings, "piper_model", "").strip()
    return Path(path).expanduser() if path else default_model_path()


def piper_binary() -> Path | None:
    path = getattr(settings, "piper_bin", "").strip()
    if path:
        explicit = Path(path).expanduser()
        if explicit.is_file() and os.access(explicit, os.X_OK):
            return explicit
        # Suporte a PIPER_BIN=piper ou a um executável no PATH.
        found = shutil.which(path)
        return Path(found) if found else None
    bundled = default_bin_path()
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return bundled
    found = shutil.which("piper")
    return Path(found) if found else None


def piper_status() -> tuple[bool, str]:
    """Diagnóstico sem abrir processos, sem downloads e sem expor dados."""
    model = piper_model_path()
    config = Path(str(model) + ".json")
    if not model.is_file() or model.stat().st_size < 1_000_000:
        return False, f"Modelo não encontrado: {model}"
    if not config.is_file():
        return False, f"Configuração da voz não encontrada: {config}"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        language = data.get("language", {}).get("code")
        if language not in ("pt_BR", "pt-BR"):
            return False, f"Modelo não identificado como pt-BR: {language!r}"
    except (OSError, ValueError, AttributeError, TypeError):
        return False, "Configuração ONNX/JSON inválida"
    binary = piper_binary()
    if binary is None:
        return False, "Executável Piper indisponível (rode scripts/setup_piper_voice.py)"
    return True, f"Voz {VOICE_NAME} pronta (offline)"


def synthesize_piper(text: str) -> Path | None:
    """Gera WAV com limite de tempo e sem shell; retorna None se indisponível."""
    ready, reason = piper_status()
    if not ready:
        logger.warning("Piper não configurado: %s", reason)
        return None

    model = piper_model_path()
    binary = piper_binary()
    if binary is None:
        return None

    fd, filename = tempfile.mkstemp(prefix="jarvis_piper_", suffix=".wav")
    os.close(fd)
    output = Path(filename)
    # O bundle legado inclui espeak-ng-data no diretório do binário.
    # Quando o piper vem do PATH, a pasta atual do JARVIS não é alterada.
    bundle_dir = default_bin_path().parent
    cwd = str(bundle_dir) if binary == default_bin_path() else None
    succeeded = False
    try:
        process = subprocess.run(
            [
                str(binary), "--model", str(model.resolve()),
                "--config", str(Path(str(model) + ".json").resolve()),
                "--output_file", str(output),
            ],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=max(5, int(getattr(settings, "piper_timeout", 90))),
            cwd=cwd,
            check=False,
        )
        if process.returncode != 0:
            logger.warning(
                "Piper falhou (código %s): %s",
                process.returncode,
                process.stderr.decode("utf-8", "replace")[-300:],
            )
            return None
        if output.stat().st_size < 44:
            logger.warning("Piper produziu WAV vazio.")
            return None
        with output.open("rb") as wav:
            header = wav.read(12)
        if header[:4] != b"RIFF" or header[8:] != b"WAVE":
            logger.warning("Piper produziu arquivo sem cabeçalho WAV.")
            return None
        # Reprodução pode ser assíncrona, então não apagar antes do pygame.
        atexit.register(output.unlink, missing_ok=True)
        succeeded = True
        return output
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        logger.warning("Falha ao executar Piper: %s", exc)
        return None
    finally:
        # Arquivos incompletos não se acumulam após falhas/timeout.
        if not succeeded:
            output.unlink(missing_ok=True)
