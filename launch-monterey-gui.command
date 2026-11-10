#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "Ambiente non installato; consulta docs/MONTEREY.md"
  read -r -p "Premi Invio..." _
  exit 1
fi
exec .venv/bin/python -m apple_photos_to_immich.gui
