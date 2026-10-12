#!/usr/bin/env python3
"""Instalador explícito e sem root do Piper Linux x86-64 + voz brasileira.

O binário independente evita depender da versão Python 3.14. Downloads
somente quando o usuário executa este script, nunca durante uma resposta.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from voice.piper_engine import VOICE_NAME, default_bin_path, default_model_path, piper_status

RELEASE_URL = (
    "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/"
    "piper_linux_x86_64.tar.gz"
)
RELEASE_LENGTH = 26460462
VOICE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "pt/pt_BR/faber/medium/"
)
VOICE_SIZE = 63201294
VOICE_SHA256 = "858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7"


def _download(url: str, dest: Path, max_size: int, expected_size: int | None = None,
              sha256: str | None = None) -> None:
    if not url.startswith("https://"):
        raise ValueError("O download precisa usar HTTPS")
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + ".partial")
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(url, timeout=50) as response, temp.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    raise ValueError("Download excedeu o tamanho permitido")
                output.write(chunk)
                digest.update(chunk)
        if expected_size is not None and total != expected_size:
            raise ValueError(f"Download incompleto: {total} != {expected_size}")
        if sha256 and digest.hexdigest() != sha256:
            raise ValueError("SHA-256 do modelo não corresponde ao arquivo oficial")
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)


def _safe_extract_piper(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            if ((name != "piper" and not name.startswith("piper/"))
                    or ".." in Path(name).parts
                    or member.isdev() or member.isfifo()):
                raise ValueError(f"Arquivo inesperado no pacote: {name!r}")
        # Python >= 3.12: bloqueia links para fora da pasta, setuid, etc.
        tar.extractall(path=destination, filter="data")


def install(*, model_only: bool = False, force: bool = False) -> None:
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise RuntimeError(
            "Instalador automático só para Linux x86_64. "
            "Em outro sistema, instale Piper e configure PIPER_BIN."
        )
    binary = default_bin_path()
    model = default_model_path()
    config = Path(str(model) + ".json")

    if not model_only and (force or not binary.is_file()):
        print("Baixando o Piper Linux x86_64 (26 MB)...", flush=True)
        with tempfile.TemporaryDirectory(prefix="jarvis_piper_setup_") as tmp:
            archive = Path(tmp) / "piper_linux_x86_64.tar.gz"
            _download(RELEASE_URL, archive, max_size=30_000_000,
                      expected_size=RELEASE_LENGTH)
            _safe_extract_piper(archive, binary.parent.parent)
        if not binary.is_file():
            raise RuntimeError("O executável Piper não veio no pacote")
        binary.chmod(binary.stat().st_mode | 0o100)

    if force or not model.is_file() or model.stat().st_size != VOICE_SIZE:
        print("Baixando voz brasileira Faber medium (63 MB)...", flush=True)
        _download(VOICE_URL + f"{VOICE_NAME}.onnx", model,
                  max_size=65_000_000, expected_size=VOICE_SIZE,
                  sha256=VOICE_SHA256)
    if force or not config.is_file():
        print("Baixando a configuração pt-BR...", flush=True)
        _download(VOICE_URL + f"{VOICE_NAME}.onnx.json", config,
                  max_size=100_000)
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        if data["language"]["code"] != "pt_BR":
            raise ValueError("Não é uma voz brasileira")
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("A configuração da voz pt-BR é inválida") from exc
    ready, detail = piper_status()
    if not ready:
        raise RuntimeError(detail)
    print("Piper pronto! " + detail)
    print('Teste: TTS_PROVIDER=piper python -c '
          '"from voice.text_to_speech import speak; speak('
          "'Olá, sou o Jarvis.'"
          ')"')


def main() -> int:
    parser = argparse.ArgumentParser(description="Instala Piper pt-BR offline")
    parser.add_argument("--model-only", action="store_true",
                        help="Baixa ONNX e JSON se já tem Piper")
    parser.add_argument("--force", action="store_true",
                        help="Baixa novamente o runtime e o modelo")
    args = parser.parse_args()
    try:
        install(model_only=args.model_only, force=args.force)
    except Exception as exc:
        print("Instalação do Piper falhou: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
