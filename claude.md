# QScript Coding Assistant Build Notes

This project replaces the previous Gradio prototype in `draft/app.py` with a production-oriented FastAPI REST backend and a React TypeScript frontend.

## Resulting Structure

```text
backend/
  app/
    core/config.py          # environment-driven settings
    main.py                 # FastAPI application and API routes
    models/schemas.py       # Pydantic request/response contracts
    services/chat.py        # chat orchestration and streaming events
    services/spec_context.py# local spec/PDF/text prompt assembly
    services/vllm_client.py # OpenAI-compatible vLLM client
    services/source_output.py
    services/html.py
  requirements.txt
  run-api.sh

frontend/
  src/App.tsx               # React TypeScript chat client
  src/main.tsx
  src/styles.css
  package.json
  vite.config.ts

run-api.sh
run-frontend.sh
run-backend-qwen3-coder-30b.sh # vLLM model server launcher
```

## Backend Creation Steps

1. Create the backend folder and FastAPI package:

```bash
mkdir -p backend/app/core backend/app/models backend/app/services
```

2. Move reusable behavior from the prototype into backend services:

```text
spec_context.py     scans spec/specs/Spec/Specs, reads PDFs, reads Codierrichtlinien.txt, estimates prompt tokens
source_output.py    strips thinking/markdown, extracts final source, saves generated TXT files
vllm_client.py      calls the OpenAI-compatible vLLM endpoint from run-backend-qwen3-coder-30b.sh
chat.py             builds prompts, calls vLLM, streams SSE responses, renders source as HTML
```

3. Expose production REST endpoints in `backend/app/main.py`:

```text
GET  /health
GET  /api/config
GET  /api/backend
GET  /api/specs
POST /api/chat
POST /api/chat/stream
POST /api/chat/continue
```

4. Configure the backend with environment variables:

```bash
cp backend/.env.example backend/.env
```

Important values:

```bash
VLLM_BASE_URL=http://127.0.0.1:8042/v1
VLLM_API_KEY=dummy
VLLM_MODEL=Qwen/Qwen3-Coder-30B-A3B-Instruct
DGX_VLLM_MODEL=Qwen/Qwen3-Coder-30B-A3B-Instruct
VLLM_NUM_CTX=32768
VLLM_RESERVED_OUTPUT_TOKENS=8192
SPEC_PROMPT_TOKEN_BUDGET=9830
SPEC_PROMPT_MAX_CONTEXT_FRACTION=0.30
PROJECT_ROOT=..
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173","http://192.168.1.196:5173"]
```

5. Install backend dependencies:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

6. Start the DGX vLLM backend first:

```bash
chmod +x run-backend-qwen3-coder-30b.sh
./run-backend-qwen3-coder-30b.sh
```

7. Start the FastAPI backend:

```bash
cd ..
chmod +x run-api.sh
./run-api.sh
```

The API runs on `http://127.0.0.1:8000` by default.

## Frontend Creation Steps

1. Create a Vite React TypeScript application under `frontend/`.

2. Implement `frontend/src/App.tsx` as a REST/SSE client:

```text
GET  /api/config        loads model defaults
GET  /api/backend       checks vLLM model availability
GET  /api/specs         scans local spec files
POST /api/chat/stream   streams generated source code as Server-Sent Events (SSE)
POST /api/chat/continue continues the previous source output
```

3. Render assistant output as sanitized HTML, not Markdown:

```text
The backend returns assistant_html.
The frontend sanitizes it with DOMPurify.
Generated code is shown inside <pre class="generated-code"><code>...</code></pre>.
Markdown rendering libraries are not used.
```

4. Install and run the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://127.0.0.1:5173` by default.

## Full Local Startup Order

1. Start vLLM on DGX Spark:

```bash
./run-backend-qwen3-coder-30b.sh
```

2. Start FastAPI:

```bash
./run-api.sh
```

For explicit environment defaults, use one of these instead:

```bash
# DGX Spark default: vLLM on 8042 with Qwen3-Coder 30B A3B
./run-api-dgx.sh

# M1 Mac default: Ollama on 11434 with qwen2.5-coder:3b
./run-api-ollama.sh
```

`ollama show qwen2.5-coder:3b` reports a context length of 32768. `run-api-ollama.sh` defaults to `qwen2.5-coder:3b` and `VLLM_NUM_CTX=32768` for the M1 Mac. Spec text is capped to 9830 tokens, which is 30% of that context window. `run-api-dgx.sh` also keeps `VLLM_NUM_CTX=32768` to match the DGX vLLM server command.

The React UI also includes a backend switcher. It sends the selected `provider_id` with each chat request:

```text
dgx_vllm_qwen       -> http://127.0.0.1:8042/v1, model Qwen/Qwen3-Coder-30B-A3B-Instruct
m1_ollama_qwen_coder -> http://127.0.0.1:11434/v1, model qwen2.5-coder:3b
```

The React UI also includes an API-location switcher:

```text
M1 Mac local API -> same-origin /api through the Vite proxy to http://127.0.0.1:8000
DGX Spark LAN API -> http://192.168.1.196:8080
```

Run `./run-api-dgx.sh` on the DGX Spark to expose FastAPI on `http://192.168.1.196:8080`. The script allows CORS from the React dev URLs `http://localhost:5173`, `http://127.0.0.1:5173`, and `http://192.168.1.196:5173`.

For DGX Spark, start the new vLLM model server helper when you want the current Qwen3-Coder 30B model:

```bash
chmod +x run-backend-qwen3-coder-30b.sh
./run-backend-qwen3-coder-30b.sh
```

This helper runs:

```bash
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct \
  --host 0.0.0.0 \
  --port 8042 \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.80 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
```

The FastAPI app reserves 8192 tokens for generation and caps loaded specification context to `min(SPEC_PROMPT_TOKEN_BUDGET, 30% of context)`. With the default 32768-token context this is 9830 spec tokens.

The UI also includes a spec-source switcher. It sends the selected `spec_source_id` with each scan and chat request:

```text
project_spec        -> ./spec
usb_untitled_spec  -> /media/peterstroessler/C6B5-FBEC/spec
```

The USB option expects the mounted external device `C6B5-FBEC` with this structure:

```text
/media/peterstroessler/C6B5-FBEC/spec/
  pdfs/
  pdfs-txt/
  reports/
```

On DGX/Linux the same stick is normally mounted as one of these paths:

```text
/media/$USER/C6B5-FBEC/spec
/run/media/$USER/C6B5-FBEC/spec
/mnt/C6B5-FBEC/spec
```

The backend auto-detects those common paths. To force a path:

```bash
export USB_SPEC_ROOT=/media/$USER/C6B5-FBEC/spec
```

`run-api-dgx.sh` defaults to `APP_DEFAULT_SPEC_SOURCE=usb_untitled_spec` so the DGX Spark setup uses the external stick by default.

3. Start React:

```bash
./run-frontend.sh
```

4. Open:

```text
http://127.0.0.1:5173
```

## Production Notes

- Run FastAPI without `--reload` in production.
- Set `CORS_ORIGINS` to the exact frontend domain.
- Put TLS and compression at the reverse proxy layer.
- Keep `VLLM_BASE_URL` private to the backend network when deployed.
- Store generated text files in a controlled volume instead of the repository folder.
- Add authentication before exposing the API outside a trusted local network.
- The previous Gradio app remains in `draft/app.py` only as reference material; it is not used by the new app.
