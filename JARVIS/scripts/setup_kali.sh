#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -r /etc/os-release ]]; then
  echo "Não foi possível identificar a distribuição Linux." >&2
  exit 1
fi
. /etc/os-release
case "${ID:-}:${ID_LIKE:-}" in
  kali:*|debian:*|*:debian*) echo "[OK] Distribuição Debian/Kali detectada: ${PRETTY_NAME:-$ID}" ;;
  *) echo "[AVISO] Este script foi projetado para Debian/Kali; detectado: ${PRETTY_NAME:-desconhecido}" ;;
esac

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "[ERRO] Python 3 ausente. Instale manualmente: sudo apt install python3 python3-venv python3-pip"
  exit 1
fi
echo "[OK] $($PYTHON_BIN --version)"
PY_MINOR="$($PYTHON_BIN -c 'import sys; print(sys.version_info.minor)')"
if (( PY_MINOR > 13 )); then
  echo "[AVISO] Python 3.$PY_MINOR é muito recente para algumas bibliotecas de áudio. Se o pip falhar, use Python 3.12 ou 3.13 para criar .venv."
fi

if ! "$PYTHON_BIN" -c 'import venv' >/dev/null 2>&1; then
  echo "[ERRO] módulo venv ausente. Instale manualmente: sudo apt install python3-venv"
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  echo "Criando ambiente virtual em .venv..."
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if command -v ollama >/dev/null 2>&1; then
  echo "[OK] Ollama encontrado."
  if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -Fxq 'qwen3.5:9b'; then
    echo "[OK] qwen3.5:9b instalado."
  else
    echo "[PENDENTE] Execute manualmente: ollama pull qwen3.5:9b"
  fi
else
  echo "[PENDENTE] Ollama não encontrado. Instale pela documentação oficial; este script não executa curl | sh."
fi

if command -v wpctl >/dev/null 2>&1 || command -v pactl >/dev/null 2>&1; then
  echo "[OK] Controle de áudio encontrado."
else
  echo "[PENDENTE] Instale PipeWire/PulseAudio. Em Kali, confira: sudo apt install pipewire-audio pulseaudio-utils"
fi
if ! command -v xdg-open >/dev/null 2>&1; then
  echo "[PENDENTE] xdg-open ausente. Em Kali: sudo apt install xdg-utils"
fi
echo "Setup Python concluído. Rode: .venv/bin/python main.py --doctor"
