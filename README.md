# QScript Coding Assistant

Local DGX Spark setup for:

- vLLM with `Qwen/Qwen3-Coder-30B-A3B-Instruct`
- FastAPI backend
- React/Vite frontend

## Install Environment

Create and populate the root `.venv`:

```bash
./install.sh
```

The installer uses Python 3.12, keeps the uv cache in the project, installs the vLLM/backend dependencies, and creates `.env` with DGX defaults.

## Start Services

Start the services in this order.

### 1. vLLM Backend

From the project root:

```bash
chmod +x run-backend-qwen3-coder-30b.sh
./run-backend-qwen3-coder-30b.sh
```

vLLM runs on:

```text
http://127.0.0.1:8042/v1
```

Check it with:

```bash
curl -sS http://127.0.0.1:8042/v1/models
```

### 2. FastAPI Backend

From the project root:

```bash
./run-api-dgx.sh
```

FastAPI runs on:

```text
http://127.0.0.1:8080
```

Check it with:

```bash
curl -sS http://127.0.0.1:8080/health
curl -sS "http://127.0.0.1:8080/api/backend?provider_id=dgx_vllm_qwen"
```

### 3. React Frontend

From the project root:

```bash
./run-frontend.sh
```

React/Vite runs on:

```text
http://127.0.0.1:5173
```

On the DGX network it may also be available at:

```text
http://192.168.1.196:5173
```

## Start Services With tmux

Use these commands to keep all three services running in the background:

```bash
tmux new-session -d -s qscript-vllm 'cd /data/Projects/qscript-coding-assistant && ./run-backend-qwen3-coder-30b.sh 2>&1 | tee /tmp/qscript-vllm.log'
tmux new-session -d -s qscript-api 'cd /data/Projects/qscript-coding-assistant && ./run-api-dgx.sh 2>&1 | tee /tmp/qscript-api.log'
tmux new-session -d -s qscript-frontend 'cd /data/Projects/qscript-coding-assistant && ./run-frontend.sh 2>&1 | tee /tmp/qscript-frontend.log'
```

List sessions:

```bash
tmux list-sessions
```

Stop services:

```bash
tmux kill-session -t qscript-vllm
tmux kill-session -t qscript-api
tmux kill-session -t qscript-frontend
```

View logs:

```bash
tail -n 120 /tmp/qscript-vllm.log
tail -n 120 /tmp/qscript-api.log
tail -n 120 /tmp/qscript-frontend.log
```

## Important URLs

```text
vLLM models:      http://127.0.0.1:8042/v1/models
FastAPI health:   http://127.0.0.1:8080/health
FastAPI backend:  http://127.0.0.1:8080/api/backend?provider_id=dgx_vllm_qwen
Frontend:         http://127.0.0.1:5173
```

Note: `http://127.0.0.1:8080/v1/models` is not a valid route. Port `8080` is FastAPI. The vLLM OpenAI-compatible API is on port `8042`.
