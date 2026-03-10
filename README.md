# Infinity-Chat

Infinity-Chat is a cross-platform AI chat application with:
- FastAPI backend (async + SSE streaming)
- Streamlit frontend (interactive control console)
- Groq primary inference + OpenRouter failover
- Real persistent local storage using SQLite

## Highlights

- Smart failover: Groq -> OpenRouter on `429` / `5xx`
- Route modes: `speed`, `balanced`, `economy`
- Persona profiles from `config.yaml`
- Real-time streaming tokens in UI
- Persistent chat history saved on disk
- Works on Linux, Windows 11, and Android browser (LAN)

## Tech Stack

- Language: Python 3.11+
- Backend: FastAPI, Uvicorn, HTTPX
- Frontend: Streamlit, Requests
- Validation/config: Pydantic, python-dotenv, PyYAML
- Storage: SQLite (`sqlite3` stdlib)
- Environment tooling: `.venv` + optional Pixi

## Persistent Storage (Real, Local, Visible)

All chats are stored in a local SQLite DB file:

- `data/infinity_chat.db`

Backend tables:
- `chat_sessions` (session metadata)
- `chat_messages` (user/assistant messages)
- `request_logs` (latency, provider, failover metrics)

API endpoints for persistence:
- `GET /storage/info` -> shows exact DB path and file size
- `GET /sessions` -> list saved sessions
- `GET /sessions/{session_id}/messages` -> load message history
- `DELETE /sessions/{session_id}` -> delete a session

UI persistence features:
- Shows DB path and size in sidebar
- Load/delete saved sessions from sidebar
- New session creates a new persistent session ID

## Architecture

```text
Browser (Desktop / Android)
   |
   v
Streamlit UI (ui.py :8501)
   |
   | POST /chat/stream (SSE)
   v
FastAPI API (main.py :8080)
   |
   +--> Provider Router (speed/balanced/economy)
   |      - Groq
   |      - OpenRouter
   |
   +--> SQLite Persistence (data/infinity_chat.db)
```

## Project Structure

```text
Infinity-Chat/
├── main.py
├── ui.py
├── config.yaml
├── .env.example
├── requirements.txt
├── pixi.toml
├── setup.sh
├── start_app.sh
├── stop_app.sh
├── setup.bat
├── start_app.bat
├── stop_app.bat
├── data/
│   └── .gitkeep
└── README.md
```

## Setup

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd Infinity-Chat
cp .env.example .env
```

### 2. Get real API keys

Groq:
- Open `https://console.groq.com/`
- Sign in
- Go to `https://console.groq.com/keys`
- Create a new API key

OpenRouter:
- Open `https://openrouter.ai/`
- Sign in
- Go to `https://openrouter.ai/docs/api-keys`
- Create a new API key

Use the keys exactly as raw values in `.env`. Do not wrap them in quotes.

Correct:

```env
GROQ_API_KEY=your_real_groq_key
OPENROUTER_API_KEY=your_real_openrouter_key
```

Avoid:

```env
GROQ_API_KEY="your_real_groq_key"
OPENROUTER_API_KEY='your_real_openrouter_key'
```

### 3. Add API keys to `.env`

Linux/macOS:

```bash
nano .env
```

Windows 11 (CMD):

```bat
notepad .env
```

Set at least:

```env
GROQ_API_KEY=your_real_groq_key
OPENROUTER_API_KEY=your_real_openrouter_key
```

Optional runtime values already included in `.env.example`:
- `BACKEND_HOST=0.0.0.0`
- `BACKEND_PORT=8080`
- `UI_HOST=0.0.0.0`
- `UI_PORT=8501`
- `SQLITE_PATH=data/infinity_chat.db`

### 4. Install

Linux/macOS:

```bash
./setup.sh
```

Windows 11 (CMD):

```bat
setup.bat
```

### Python version note

This project should be installed with Python `3.11`, `3.12`, or `3.13`.

Reason:
- some dependencies, especially `pydantic-core`, may fail to build on Python `3.14` because upstream Rust bindings may not support it yet

If installation fails on Linux because your default `python3` is `3.14`, this repository's `setup.sh` now automatically prefers:
- `python3.13`
- then `python3.12`
- then `python3.11`

On a machine like CachyOS where `python3.12` is available, recover with:

```bash
cd ~/work/projects/Infinity-Chat
rm -rf .venv
./setup.sh
```

You can verify the interpreter version with:

```bash
.venv/bin/python --version
```

## Run

Linux/macOS:

```bash
./start_app.sh
```

Windows 11:

```bat
start_app.bat
```

Open:
- UI: `http://127.0.0.1:8501`
- API: `http://127.0.0.1:8080`

Stop:
- Linux/macOS: `./stop_app.sh`
- Windows: `stop_app.bat`

## Cross-Platform Details

### Linux (any distro)
- Uses Python `venv` and shell scripts only
- No sudo required
- Works as long as Python 3.11+ and internet access are available

### Windows 11
- Uses `.bat` scripts and local `.venv`
- No admin rights required for normal local run
- Background start done via `start /b`

### Android
- Android runs the UI in browser; backend/UI still run on your desktop/laptop
- Start app with host `0.0.0.0` (already default in scripts)
- Connect Android and host to same Wi-Fi
- Open `http://<HOST_LAN_IP>:8501` in Android browser
- API keys are still added only on the host machine in `.env`
- Android does not store or need the provider keys locally

## API Endpoints

- `GET /health`
- `GET /profiles`
- `GET /metrics`
- `GET /storage/info`
- `GET /sessions`
- `GET /sessions/{session_id}/messages`
- `DELETE /sessions/{session_id}`
- `POST /chat` (non-stream)
- `POST /chat/stream` (SSE stream)

## Notes

- `.env` is excluded from git.
- Local SQLite DB files are excluded from git.
- For production, add auth, stricter CORS, and encrypted secrets management.
