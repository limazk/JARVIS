#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$PROJECT_DIR/deploy/linux/jarvis.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/jarvis.service"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Este instalador é exclusivo para Linux." >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl não encontrado; systemd --user é necessário para esta instalação." >&2
  exit 1
fi

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3 não encontrado. Rode scripts/setup_kali.sh primeiro." >&2
  exit 1
fi

mkdir -p "$UNIT_DIR"
escape_sed() { printf '%s' "$1" | sed 's/[&|]/\\&/g'; }
PROJECT_ESCAPED="$(escape_sed "$PROJECT_DIR")"
PYTHON_ESCAPED="$(escape_sed "$PYTHON_BIN")"
sed -e "s|@PROJECT_DIR@|$PROJECT_ESCAPED|g" -e "s|@PYTHON@|$PYTHON_ESCAPED|g" "$TEMPLATE" > "$UNIT_FILE"

systemctl --user daemon-reload
systemctl --user enable jarvis.service
systemctl --user restart jarvis.service
echo "Serviço instalado em $UNIT_FILE"
echo "Status: systemctl --user status jarvis"
