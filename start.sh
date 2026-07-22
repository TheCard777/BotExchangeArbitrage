#!/usr/bin/env bash
set -e
trap 'echo ""; read -p "Appuie sur Entree pour fermer cette fenetre..." _' EXIT

cd "$(dirname "$0")"

# Same guard as install.sh: catch running from inside the archive.
if [ ! -f main.py ]; then
  echo "Il manque des fichiers du bot ici. Tu as sans doute lance start.sh"
  echo "sans decompresser l'archive."
  echo "-> Clic droit sur le .zip/.rar -> Extraire tout, ouvre le dossier"
  echo "   extrait, puis lance ./install.sh puis ./start.sh depuis la."
  exit 1
fi

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
