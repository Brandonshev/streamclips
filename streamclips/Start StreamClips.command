#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  bundled_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
  if [[ -x "$bundled_python" ]]; then
    "$bundled_python" -m venv .venv
  else
    python3 -m venv .venv
  fi
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python launch.py
