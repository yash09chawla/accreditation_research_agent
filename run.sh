#!/usr/bin/env bash
# Start the Accreditation Research Agent API + test UI on http://127.0.0.1:${PORT:-8100}
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/uvicorn accreditation_engine.api:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8100}" "$@"
