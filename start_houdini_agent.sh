#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# The external Agent uses its own Python, not Houdini's embedded Python.
unset PYTHONHOME PYTHONPATH
PYTHON="${HAGENT_PYTHON:-}"
if [[ -z "$PYTHON" && -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
fi
if [[ -z "$PYTHON" ]]; then
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
            PYTHON="$(command -v "$candidate")"
            break
        fi
    done
fi
if [[ -z "$PYTHON" ]]; then
    printf '%s\n' 'Python 3.11+ is required. On Rocky 9: sudo dnf install python3.11 python3.11-pip' >&2
    exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    printf '%s\n' 'The selected Python is too old; set HAGENT_PYTHON to Python 3.11+.' >&2
    exit 1
fi
if [[ "${1:-}" == "--setup" ]]; then
    "$PYTHON" -m venv "$ROOT/.venv"
    "$ROOT/.venv/bin/python" -m pip install --upgrade pip
    exec "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements-linux.txt"
fi
exec "$PYTHON" -m houdini_agent.launcher.linux "$@"
