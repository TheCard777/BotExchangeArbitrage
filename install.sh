#!/usr/bin/env bash
set -e
trap 'echo ""; read -p "Appuie sur Entree pour fermer cette fenetre..." _' EXIT

cd "$(dirname "$0")"

# Guard against the most common mistake: running install.sh from INSIDE the
# zip/rar archive (WinRAR extracts just this one file to a temp folder). If the
# bot's files aren't next to this script, tell the user to extract first.
if [ ! -f requirements.txt ] || [ ! -f setup_wizard.py ]; then
  echo "======================================================================"
  echo "  Il manque des fichiers du bot dans ce dossier."
  echo ""
  echo "  Tu as probablement lance install.sh SANS decompresser l'archive."
  echo ""
  echo "  -> Clic droit sur le fichier .zip / .rar recu -> \"Extraire tout\""
  echo "     (Extract all). Ouvre le dossier extrait, PUIS lance install.sh"
  echo "     depuis CE dossier-la."
  echo "======================================================================"
  exit 1
fi

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
# In Git Bash (mintty) getpass can't hide the API-key input; winpty gives a
# real console so the key stays masked. Fall back to a plain run otherwise.
if [ -n "$MSYSTEM" ] && command -v winpty >/dev/null 2>&1; then
  winpty "$VENV_PYTHON" setup_wizard.py
else
  "$VENV_PYTHON" setup_wizard.py
fi
