#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/backend"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:11434/v1}" \
VLLM_MODEL="${VLLM_MODEL:-qwen2.5-coder:3b}" \
M1_OLLAMA_MODEL="${M1_OLLAMA_MODEL:-qwen2.5-coder:3b}" \
VLLM_NUM_CTX="${VLLM_NUM_CTX:-32768}" \
SPEC_PROMPT_TOKEN_BUDGET="${SPEC_PROMPT_TOKEN_BUDGET:-9830}" \
SPEC_PROMPT_MAX_CONTEXT_FRACTION="${SPEC_PROMPT_MAX_CONTEXT_FRACTION:-0.30}" \
uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8000}" --reload
