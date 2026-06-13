#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Keep uv/pip cache writes inside the project so setup works on the DGX sandbox.
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_ROOT/.uv-cache}"

python3 -m pip install --user uv

uv venv "$PROJECT_ROOT/.venv" --python 3.12 --seed
source "$PROJECT_ROOT/.venv/bin/activate"

# Install the vLLM/Qwen project dependencies from pyproject.toml into root .venv.
uv sync --active

# Keep the FastAPI requirements explicit for people reading the backend folder.
uv pip install -r "$PROJECT_ROOT/backend/requirements.txt"

if [ ! -f "$PROJECT_ROOT/.env" ]; then
  cat > "$PROJECT_ROOT/.env" <<'ENV'
APP_ENV=development
APP_DEFAULT_PROVIDER=dgx_vllm_qwen
APP_DEFAULT_SPEC_SOURCE=usb_untitled_spec
PROJECT_ROOT=/data/Projects/qscript-coding-assistant
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173","http://192.168.1.196:5173"]
USB_SPEC_ROOT=/media/peterstroessler/C6B5-FBEC/spec
VLLM_BASE_URL=http://127.0.0.1:8042/v1
DGX_VLLM_BASE_URL=http://127.0.0.1:8042/v1
VLLM_MODEL=Qwen/Qwen3-Coder-30B-A3B-Instruct
DGX_VLLM_MODEL=Qwen/Qwen3-Coder-30B-A3B-Instruct
VLLM_NUM_CTX=32768
VLLM_RESERVED_OUTPUT_TOKENS=8192
VLLM_MAX_TOKENS=8192
VLLM_TIMEOUT_SECONDS=600
SPEC_PROMPT_TOKEN_BUDGET=9830
SPEC_PROMPT_MAX_CONTEXT_FRACTION=0.30
ENV
fi

echo "Environment ready: source $PROJECT_ROOT/.venv/bin/activate"
