#!/bin/bash
# SBA-Launcher — macOS/Linux Dev-Start.
# Auf dem headless VPS nicht lauffaehig (kein Display/Tkinter); dient als
# Vorlage fuer X-Forwarding-/Heimrechner-Dev. Windows-Workflow nutzt start.bat.
set -e
cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
  uv sync
  uv run python launcher.py
else
  echo "[FEHLER] 'uv' fehlt. Installieren:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi