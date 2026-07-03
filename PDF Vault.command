#!/bin/zsh
# Double-click this file in Finder to launch PDF Vault.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Setting up PDF Vault for first use..."
  /usr/local/bin/python3 -m venv .venv || python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python app.py
