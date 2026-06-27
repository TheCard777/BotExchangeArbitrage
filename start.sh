#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ -f .venv/bin/python ]; then
  VENV_PYTHON=.venv/bin/python
elif [ -f .venv/Scripts/python.exe ]; then
  VENV_PYTHON=.venv/Scripts/python.exe
else
  VENV_PYTHON=""
fi

if [ ! -f .env ] || [ -z "$VENV_PYTHON" ]; then
  echo "Le bot n'est pas encore configure."
  echo "Lance d'abord : ./install.sh"
  exit 1
fi

"$VENV_PYTHON" main.py
