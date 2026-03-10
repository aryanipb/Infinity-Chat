# Infinity-Chat

**Infinity-Chat** is a cross-platform AI chat system with adaptive model routing, streaming responses, and smart failover.

It runs on:
- Windows 11
- Linux distributions (Ubuntu, Debian, Fedora, Arch, etc.)
- Android (via browser over same LAN)

Core runtime is Python with FastAPI + Streamlit, and provider orchestration across Groq and OpenRouter.

## 1. Project Goals

Infinity-Chat is built to deliver a resilient chat experience under real-world API constraints.

Design objectives:
- Keep response flow alive during provider throttling/outages
- Make behavior tunable (speed vs cost vs balanced)
- Support profile-based personas for different engineering workflows
- Keep setup permission-safe (no sudo required)
- Provide simple operation across desktop and mobile clients

## 2. What Makes This Version Unique

Compared to a basic chatbot wrapper, this build includes:

1. Adaptive routing engine
- `speed`: Groq -> OpenRouter
- `economy`: OpenRouter -> Groq
- `balanced`: intent-aware order (code-heavy prompts prefer Groq first)

2. Smart failover with policy controls
- Auto-fallback on `429` and `5xx`
- Non-retryable errors stop immediately with explicit diagnostics
- Optional offline fallback response if all providers fail

3. Persona profile system
- Configurable profiles in `config.yaml`
- Example profiles:
  - `open_source_architect`
  - `rapid_prototyper`
  - `production_guardian`

4. Live telemetry and observability
- `/metrics` endpoint with rolling request window
- Provider usage counts, fallback counts, average latency
- Recent request log snapshots

5. Advanced Streamlit control console
- Runtime controls: route mode, provider forcing, temperature, max tokens
- Profile selection from backend
- Import/export chat history (JSON, Markdown)
- Preset prompts for common workflows
- Real-time stream debug panel (status/fallback path)

6. Cross-platform app operations
- Linux scripts: `setup.sh`, `start_app.sh`, `stop_app.sh`
- Windows scripts: `setup.bat`, `start_app.bat`, `stop_app.bat`
- Android access via LAN URL on browser

## 3. Architecture

```text
[Browser / Desktop / Android]
            |
            v
 [Streamlit UI :8501]  <-- SSE events (meta/status/token/done/error)
            |
            v
 [FastAPI Backend :8080]
            |
            +--> Provider Router (speed/balanced/economy)
            |
            +--> Groq (primary in speed mode)
            |
            +--> OpenRouter (primary in economy mode)
            |
            +--> Optional offline fallback message
```

## 4. Repository Structure

```text
Infinity-Chat/
├── main.py           # FastAPI backend (routing, failover, SSE, metrics)
├── ui.py             # Streamlit control console
├── config.yaml       # persona, profiles, models, routing defaults
├── .env.example      # environment template
├── requirements.txt  # Python dependencies
├── pixi.toml         # pixi project/task config
├── setup.sh          # Linux/macOS setup
├── start_app.sh      # Linux/macOS start (background)
├── stop_app.sh       # Linux/macOS stop
├── setup.bat         # Windows setup
├── start_app.bat     # Windows start
├── stop_app.bat      # Windows stop
└── README.md
```

## 5. Technology Stack

- Language: Python 3.11+
- Backend: FastAPI, Uvicorn, HTTPX
- Frontend: Streamlit
- Streaming transport: Server-Sent Events (SSE)
- Config/Env: PyYAML, python-dotenv
- HTTP client in UI: requests
- Environment tooling: `.venv` + optional `pixi`

## 6. Build Summary (Super Short)

1. Built async FastAPI streaming endpoint with OpenAI-compatible chunk parsing.
2. Added dual-provider router with route modes and automatic failover on `429/5xx`.
3. Added persona profile system from YAML configuration.
4. Added observability endpoints (`/health`, `/profiles`, `/metrics`) and request logs.
5. Built Streamlit control console with runtime knobs + chat export/import.
6. Added Linux + Windows scripts and LAN-friendly hosting for Android browser access.

## 7. Prerequisites

Minimum:
- Python 3.11+
- Internet access for model APIs
- Groq API key
- OpenRouter API key

Optional:
- `pixi` for managed task environment

## 8. Configuration

### 8.1 Environment Variables

Copy template:

```bash
cp .env.example .env
```

Set required values:
- `GROQ_API_KEY`
- `OPENROUTER_API_KEY`

Common runtime values:
- `BACKEND_HOST=0.0.0.0`
- `BACKEND_PORT=8080`
- `UI_HOST=0.0.0.0`
- `UI_PORT=8501`

### 8.2 `config.yaml`

Main tuning keys:
- `system_prompt`
- `profiles`
- `max_history_messages`
- `default_route_mode`
- `offline_fallback_enabled`
- `groq_model`
- `openrouter_model`

## 9. Installation and Run Guide

### 9.1 Linux / macOS

```bash
cd Infinity-Chat
cp .env.example .env
./setup.sh
./start_app.sh
```

Open:
- UI: `http://127.0.0.1:8501`
- API: `http://127.0.0.1:8080`

Stop services:

```bash
./stop_app.sh
```

### 9.2 Windows 11 (CMD)

```bat
cd Infinity-Chat
copy .env.example .env
setup.bat
start_app.bat
```

Open:
- UI: `http://127.0.0.1:8501`
- API: `http://127.0.0.1:8080`

Stop services:

```bat
stop_app.bat
```

### 9.3 Android Access (Browser)

1. Run app on Linux/Windows host with `UI_HOST=0.0.0.0`.
2. Ensure phone and host are on same Wi-Fi.
3. Find host LAN IP (shown in Streamlit sidebar).
4. Open on Android browser:
   - `http://<HOST_LAN_IP>:8501`

If not reachable:
- Allow inbound local firewall rule for port `8501`
- Confirm app is listening on `0.0.0.0`

## 10. API Contract

### `GET /health`
Returns API status and provider configuration.

### `GET /profiles`
Returns available persona profiles and default route mode.

### `GET /metrics`
Returns rolling telemetry window, fallback counts, provider usage, latency.

### `POST /chat`
Non-stream response mode.

### `POST /chat/stream`
SSE streaming mode with events:
- `meta`
- `status`
- `token`
- `done`
- `error`

Example payload:

```json
{
  "message": "Design a scalable event-driven backend",
  "history": [],
  "session_id": "demo-1",
  "persona_profile": "production_guardian",
  "route_mode": "balanced",
  "temperature": 0.7,
  "max_tokens": 1024,
  "force_provider": null
}
```

## 11. Operational Behavior

### Routing modes
- `speed`: low-latency first (Groq-first)
- `economy`: free-tier first (OpenRouter-first)
- `balanced`: message-intent aware

### Failover policy
- Trigger fallback when current provider returns:
  - `429`
  - `5xx`
- Do not fallback for non-retryable request/auth errors.

### Memory policy
- UI keeps local session buffer (configurable, default 10)
- Backend trims history to `max_history_messages`

## 12. Security and Secrets

- Never commit `.env` with real keys
- Rotate keys if exposed
- Use provider dashboard limits to control spend
- Keep CORS policy strict if deploying publicly

## 13. Troubleshooting

1. API unreachable
- Check `backend.log`
- Verify port `8080` is available

2. UI reachable but no responses
- Check `streamlit.log` + `backend.log`
- Test `GET /health`
- Validate API keys

3. Fallback not occurring
- Confirm upstream failure is `429` or `5xx`
- Confirm secondary provider key is configured

4. Android cannot connect
- Ensure same network
- Check host firewall
- Verify host binding is `0.0.0.0`

## 14. Recommended GitHub Push Workflow

```bash
git init
git branch -M main
git add .
git commit -m "feat: Infinity-Chat v2 with adaptive routing and cross-platform runtime"
git remote add origin <your-repo-url>
git push -u origin main
```

## 15. License

Add your preferred license file (MIT or Apache-2.0 recommended).
