#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -f .env ] || [ ! -d .venv ]; then
  echo "Le bot n'est pas encore configure."
  echo "Lance d'abord : ./install.sh"
  exit 1
fi

.venv/bin/python main.py
