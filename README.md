# Infinity-Chat

Cloud-based AI chatbot with **smart failover** and **real-time streaming**.

- Primary engine: **Groq** (`llama-4-70b` by default)
- Secondary failover: **OpenRouter** free model (`mistral-small-3.1-24b-instruct:free` by default)
- Backend: **FastAPI** (async + SSE)
- Frontend: **Streamlit** (chat UI with session memory)

## Why This Project

`Infinity-Chat` is designed for an "always-available" chat experience.

If Groq returns a rate-limit (`429`) or server error (`5xx`), the backend automatically switches to OpenRouter so users still get a response.

## Key Features

- Smart provider failover (Groq -> OpenRouter)
- Server-Sent Events (SSE) streaming from backend to UI
- Local conversation memory in Streamlit (`last 10 messages`)
- Editable persona/system instructions via `config.yaml`
- Permission-safe setup and startup scripts (no sudo)
- High-number ports only (`8080`, `8501`)
- `pixi` environment support + `.venv` flow

## Architecture

```text
User (Browser)
   |
   v
Streamlit UI (ui.py :8501)
   |
   | HTTP POST /chat/stream (SSE)
   v
FastAPI Backend (main.py :8080)
   |
   | Try Provider 1: Groq
   |   - if 429 or 5xx -> fallback
   v
Provider 2: OpenRouter (free model)
```

### Request Lifecycle

1. User sends message in Streamlit UI.
2. UI sends prompt + recent history to FastAPI `/chat/stream`.
3. Backend builds OpenAI-style `messages` with system prompt from `config.yaml`.
4. Backend calls Groq first with streaming enabled.
5. If Groq returns `429` or `5xx`, backend switches to OpenRouter automatically.
6. Token chunks are streamed back to UI as SSE events (`status`, `token`, `done`, `error`).
7. UI renders tokens in real time and saves turn in session state memory.

## Repository Structure

```text
Infinity-Chat/
├── main.py           # FastAPI backend + SSE + failover logic
├── ui.py             # Streamlit chat interface
├── config.yaml       # Persona/system prompt + default models
├── .env.example      # API key and runtime config template
├── requirements.txt  # pip dependencies
├── pixi.toml         # pixi project and tasks
├── setup.sh          # local setup script (venv + deps + pixi install)
├── start_app.sh      # starts backend + frontend in background
├── .gitignore
└── README.md
```

## Technology Stack (Super Short)

- **Language:** Python 3.11+
- **Backend:** FastAPI, Uvicorn, HTTPX
- **Frontend:** Streamlit, Requests
- **Config/Env:** PyYAML, python-dotenv
- **Packaging:** pip (`requirements.txt`) + pixi (`pixi.toml`)

## How This Was Built (Super Short)

1. Implemented async FastAPI SSE endpoint for streaming chat tokens.
2. Added dual-provider wrapper with Groq-first strategy and automatic OpenRouter fallback on `429`/`5xx`.
3. Built Streamlit chat UI consuming SSE and maintaining local last-10-message memory.
4. Added externalized persona/model config (`config.yaml`) and environment template (`.env.example`).
5. Added setup/start scripts for no-sudo local execution and optional pixi task support.

## Prerequisites

- Linux/macOS shell (bash)
- Python 3.11+
- `pixi` installed and available in `PATH`
- Groq API key
- OpenRouter API key

## Setup Guide

### 1. Clone repository

```bash
git clone <your-repo-url>
cd Infinity-Chat
```

### 2. Create environment file

```bash
cp .env.example .env
```

Edit `.env` and set:

- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`

Optional overrides:

- `GROQ_MODEL`
- `OPENROUTER_MODEL`
- `BACKEND_URL`
- `MAX_LOCAL_MEMORY`

### 3. Install dependencies

```bash
./setup.sh
```

What it does:

- Creates local `.venv`
- Installs Python dependencies with pip
- Runs `pixi install`

## Run Guide

### Option A (recommended): start both services in background

```bash
./start_app.sh
```

This launches:

- FastAPI backend on `http://127.0.0.1:8080`
- Streamlit UI on `http://127.0.0.1:8501`

Artifacts created:

- `backend.log`, `streamlit.log`
- `backend.pid`, `streamlit.pid`

### Option B: run manually via pixi tasks

```bash
pixi run backend
# in another terminal
pixi run ui
```

## API Reference

### `GET /health`

Returns provider configuration status.

Example response:

```json
{
  "status": "ok",
  "providers": [
    {"name": "groq", "configured": true, "model": "llama-4-70b"},
    {"name": "openrouter", "configured": true, "model": "mistral-small-3.1-24b-instruct:free"}
  ]
}
```

### `POST /chat/stream`

Streams SSE events:

- `status`: provider status/fallback notices
- `token`: incremental response tokens
- `done`: completion event
- `error`: terminal error event

Request body:

```json
{
  "message": "Explain vector databases",
  "history": [
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello"}
  ],
  "session_id": "streamlit-local"
}
```

## Configuration

### `config.yaml`

You can edit:

- `persona`
- `system_prompt`
- `max_history_messages`
- `groq_model`
- `openrouter_model`

This allows fast persona and policy tuning without code changes.

## Failover Behavior

- Attempt order is fixed: `Groq` first, then `OpenRouter`
- Fallback triggers only when Groq returns:
  - `429` (rate limited)
  - `5xx` (server-side errors)
- For non-retryable errors (e.g., bad API key `401`, invalid request `400`), backend returns an `error` SSE event immediately.

## Memory Behavior

- Streamlit keeps local session state history.
- Buffer is limited to the latest 10 messages (configurable by `MAX_LOCAL_MEMORY` env var).
- Backend also trims history to `max_history_messages` from `config.yaml`.

## Operational Notes

- No root/sudo needed.
- Ports are high ports (`8080`, `8501`).
- CORS is enabled for local integration.
- Logs are plain text and easy to inspect.

## Troubleshooting

### Backend not reachable

- Check `backend.log`
- Verify port `8080` is free
- Confirm `.env` exists and keys are set

### UI loads but no response

- Check `streamlit.log` and `backend.log`
- Call health endpoint:

```bash
curl http://127.0.0.1:8080/health
```

- Ensure both API keys are valid

### Failover not happening

- Confirm Groq error is `429` or `5xx`
- Confirm OpenRouter key/model is configured in `.env`

## Security Notes

- Never commit real `.env` files
- Rotate API keys if exposed
- Keep provider limits and model availability in mind

## Local Development Commands

```bash
# syntax check
python3 -m py_compile main.py ui.py

# run backend only
python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# run UI only
streamlit run ui.py --server.port 8501 --server.address 0.0.0.0
```

## License

Choose and add your preferred license file (MIT/Apache-2.0 recommended).
