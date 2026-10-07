#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/nexus" <<EOF
#!/usr/bin/env bash
ROOT="$ROOT"
if [ -x "\$ROOT/.venv/bin/python" ]; then
  exec "\$ROOT/.venv/bin/python" "\$ROOT/main.py" --nexus "\$@"
fi
exec python3 "\$ROOT/main.py" --nexus "\$@"
EOF

chmod +x "$BIN_DIR/nexus"

echo "NEXUS instalado em: $BIN_DIR/nexus"
echo "Rode: nexus"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "Adicione ao PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
