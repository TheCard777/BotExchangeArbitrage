#!/bin/bash
set -euo pipefail

# Placeholder SessionStart hook. The repo has no dependency manifest yet
# (package.json, requirements.txt, etc). Once one is added, install
# dependencies here so tests/linters work in Claude Code on the web sessions.

if [ -f package.json ]; then
  npm install
elif [ -f requirements.txt ]; then
  pip install -r requirements.txt
elif [ -f pyproject.toml ]; then
  pip install -e .
fi
