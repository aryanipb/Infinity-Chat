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

Edit `.env` and set:
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`

### 2. Install

Linux/macOS:

```bash
./setup.sh
```

Windows 11 (CMD):

```bat
setup.bat
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
