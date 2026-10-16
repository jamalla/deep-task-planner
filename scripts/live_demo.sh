#!/usr/bin/env bash
# Live demo: run the real deep agent with your OpenAI key, in a terminal chat.
# Built for AWS CloudShell (also works on any Linux/macOS with python3).
#
#   ./scripts/live_demo.sh "Launch a small online bakery in 2 months"
#
# The key is read at a hidden prompt, lives only in this script's process,
# and is never written to disk.
set -euo pipefail
cd "$(dirname "$0")/.."

QUESTION="${1:-Launch a small online bakery in 2 months}"

if [ -z "${OPENAI_API_KEY:-}" ]; then
  read -r -s -p "Paste your OpenAI API key (hidden, not saved): " OPENAI_API_KEY
  echo
  export OPENAI_API_KEY
fi

# uv gives us Python 3.13 (same as Lambda), even if the system python is older.
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv (fast Python package manager)"
  # Inside a virtualenv (AWS CloudShell's python3 is one) --user is not allowed,
  # so try a plain install first, then --user, then uv's standalone installer.
  python3 -m pip install --quiet uv 2>/dev/null \
    || python3 -m pip install --user --quiet uv 2>/dev/null \
    || curl -LsSf https://astral.sh/uv/install.sh | sh
  hash -r
fi

VENV=/tmp/deep-task-planner-venv          # /tmp: keeps CloudShell's 1 GB home free
export UV_CACHE_DIR=/tmp/uv-cache
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> Creating Python 3.13 environment (first run takes ~1 min)"
  uv venv --quiet --python 3.13 "$VENV"
fi
uv pip install --quiet --python "$VENV/bin/python" -r requirements.txt

PYTHONPATH=. "$VENV/bin/python" scripts/live_demo.py "$QUESTION"
