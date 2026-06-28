#!/usr/bin/env bash
set -e
trap 'echo ""; read -p "Appuie sur Entree pour fermer cette fenetre..." _' EXIT

cd "$(dirname "$0")"

if [ -f .venv/bin/python ]; then
  VENV_PYTHON=.venv/bin/python
elif [ -f .venv/Scripts/python.exe ]; then
  VENV_PYTHON=.venv/Scripts/python.exe
else
  echo "Le bot n'est pas encore installe. Lance d'abord : ./install.sh"
  exit 1
fi

"$VENV_PYTHON" diagnose.py
