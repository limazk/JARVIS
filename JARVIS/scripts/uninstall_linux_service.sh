#!/usr/bin/env bash
set -euo pipefail

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/jarvis.service"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user stop jarvis.service 2>/dev/null || true
  systemctl --user disable jarvis.service 2>/dev/null || true
fi
if [[ -f "$UNIT_FILE" ]]; then
  rm -- "$UNIT_FILE"
  echo "Unidade removida: $UNIT_FILE"
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload
fi
echo "Dados, .env, memória e logs do JARVIS foram preservados."
