#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 n'est pas installe. Installe-le avant de continuer (python.org)."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creation de l'environnement Python..."
  python3 -m venv .venv
fi

echo "Installation des dependances..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo ""
.venv/bin/python setup_wizard.py
