#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"

export VLLM_USE_FLASHINFER_MOE_FP16="${VLLM_USE_FLASHINFER_MOE_FP16:-1}"
export VLLM_FLASHINFER_MOE_BACKEND="${VLLM_FLASHINFER_MOE_BACKEND:-latency}"

vllm serve "Qwen/Qwen3-Coder-30B-A3B-Instruct" \
  --host 0.0.0.0 \
  --port "${VLLM_PORT:-8042}" \
  --dtype bfloat16 \
  --max-model-len "${VLLM_MAX_MODEL_LEN:-32768}" \
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.80}" \
  --enforce-eager \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
