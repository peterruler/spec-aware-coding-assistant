#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_ROOT/.venv/bin/activate"

cd "$PROJECT_ROOT/backend"
uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8000}" --reload
