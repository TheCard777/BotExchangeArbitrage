#!/usr/bin/env bash
set -e
trap 'echo ""; read -p "Appuie sur Entree pour fermer cette fenetre..." _' EXIT

cd "$(dirname "$0")"

PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3 n'est pas installe. Installe-le avant de continuer (python.org)."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creation de l'environnement Python..."
  "$PYTHON_BIN" -m venv .venv
fi

if [ -f .venv/bin/python ]; then
  VENV_PYTHON=.venv/bin/python
  VENV_PIP=.venv/bin/pip
elif [ -f .venv/Scripts/python.exe ]; then
  VENV_PYTHON=.venv/Scripts/python.exe
  VENV_PIP=.venv/Scripts/pip.exe
else
  echo "Erreur : environnement Python introuvable apres sa creation."
  exit 1
fi

echo "Installation des dependances..."
"$VENV_PIP" install --upgrade pip -q
"$VENV_PIP" install -r requirements.txt -q

echo ""
"$VENV_PYTHON" setup_wizard.py
