#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PROJECT_ROOT/.venv/bin/activate"

cd "$PROJECT_ROOT/backend"
APP_DEFAULT_PROVIDER="${APP_DEFAULT_PROVIDER:-dgx_vllm_qwen}" \
APP_DEFAULT_SPEC_SOURCE="${APP_DEFAULT_SPEC_SOURCE:-usb_untitled_spec}" \
CORS_ORIGINS="${CORS_ORIGINS:-[\"http://localhost:5173\",\"http://127.0.0.1:5173\",\"http://192.168.1.196:5173\"]}" \
USB_SPEC_ROOT="${USB_SPEC_ROOT:-/media/${USER:-peterstroessler}/C6B5-FBEC/spec}" \
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8042/v1}" \
VLLM_MODEL="${VLLM_MODEL:-Qwen/Qwen3-Coder-30B-A3B-Instruct}" \
DGX_VLLM_MODEL="${DGX_VLLM_MODEL:-Qwen/Qwen3-Coder-30B-A3B-Instruct}" \
VLLM_NUM_CTX="${VLLM_NUM_CTX:-262144}" \
VLLM_RESERVED_OUTPUT_TOKENS="${VLLM_RESERVED_OUTPUT_TOKENS:-8192}" \
VLLM_MAX_TOKENS="${VLLM_MAX_TOKENS:-8192}" \
SPEC_PROMPT_TOKEN_BUDGET="${SPEC_PROMPT_TOKEN_BUDGET:-78643}" \
SPEC_PROMPT_MAX_CONTEXT_FRACTION="${SPEC_PROMPT_MAX_CONTEXT_FRACTION:-0.30}" \
uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8080}" --reload
