#!/usr/bin/env bash
# One-time setup: Python engine venv + Electron app dependencies.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv engine/.venv
engine/.venv/bin/pip install -q -r engine/requirements.txt
[ -f .env ] || cp .env.example .env
(cd app && npm install --no-audit --no-fund)

echo
echo "Done. Put your key in .env (MODEL_API_KEY=...), then:"
echo "  cd app && npm run dev          # real models"
echo "  cd app && npm run dev:fake     # offline fakes, mouse moves but never clicks"
