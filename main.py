import json
import os
import sqlite3
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, AsyncGenerator

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, StreamingResponse

load_dotenv()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    session_id: str | None = None
    persona_profile: str = Field(default="open_source_architect")
    route_mode: str = Field(default="balanced")
    temperature: float = Field(default=0.7, ge=0.0, le=1.5)
    max_tokens: int = Field(default=1024, ge=64, le=8192)
    force_provider: str | None = None


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str | None
    model: str


class RetryableProviderError(Exception):
    pass


class NonRetryableProviderError(Exception):
    pass


def load_config(path: str = "config.yaml") -> dict[str, Any]:
    if not os.path.exists(path):
        return {
            "persona": "Infinity-Chat",
            "system_prompt": "You are Infinity-Chat, a practical AI assistant.",
            "max_history_messages": 10,
            "default_route_mode": "balanced",
            "groq_model": "llama-4-70b",
            "openrouter_model": "mistral-small-3.1-24b-instruct:free",
            "profiles": {
                "open_source_architect": "You prioritize open-source-first technical solutions.",
            },
            "offline_fallback_enabled": True,
        }

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


CONFIG = load_config(os.getenv("CONFIG_PATH", "config.yaml"))
MAX_HISTORY_MESSAGES = int(CONFIG.get("max_history_messages", 10))
DEFAULT_ROUTE_MODE = CONFIG.get("default_route_mode", "balanced")
OFFLINE_FALLBACK_ENABLED = bool(CONFIG.get("offline_fallback_enabled", True))

REQUEST_LOG: deque[dict[str, Any]] = deque(maxlen=200)

DB_PATH = Path(os.getenv("SQLITE_PATH", "data/infinity_chat.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_LOCK = Lock()

app = FastAPI(title="Infinity-Chat API", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with DB_LOCK:
        conn = get_db_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    persona_profile TEXT NOT NULL,
                    route_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provider TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    session_id TEXT,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    fallback_used INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def derive_title(user_message: str) -> str:
    clean = " ".join(user_message.split())
    return clean[:72] if clean else "New chat"


def ensure_session(
    session_id: str,
    user_message: str,
    persona_profile: str,
    route_mode: str,
) -> None:
    now = utc_now_iso()
    title = derive_title(user_message)
    with DB_LOCK:
        conn = get_db_conn()
        try:
            existing = conn.execute(
                "SELECT session_id, title FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO chat_sessions (
                        session_id, title, persona_profile, route_mode, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, title, persona_profile, route_mode, now, now),
                )
            else:
                conn.execute(
                    """
                    UPDATE chat_sessions
                    SET persona_profile = ?, route_mode = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (persona_profile, route_mode, now, session_id),
                )
            conn.commit()
        finally:
            conn.close()


def save_chat_message(session_id: str, role: str, content: str, provider: str | None = None) -> None:
    text = content.strip()
    if not text:
        return

    now = utc_now_iso()
    with DB_LOCK:
        conn = get_db_conn()
        try:
            conn.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, provider, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, text, provider, now),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()
        finally:
            conn.close()


def persist_request_log(entry: dict[str, Any]) -> None:
    REQUEST_LOG.append(entry)
    with DB_LOCK:
        conn = get_db_conn()
        try:
            conn.execute(
                """
                INSERT INTO request_logs (
                    request_id, session_id, provider, status, fallback_used,
                    latency_ms, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.get("request_id", str(uuid.uuid4())),
                    entry.get("session_id"),
                    entry.get("provider", "unknown"),
                    entry.get("status", "error"),
                    1 if entry.get("fallback_used") else 0,
                    float(entry.get("latency_ms", 0.0)),
                    entry.get("error"),
                    utc_now_iso(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def list_sessions(limit: int = 50) -> list[dict[str, Any]]:
    with DB_LOCK:
        conn = get_db_conn()
        try:
            rows = conn.execute(
                """
                SELECT
                    s.session_id,
                    s.title,
                    s.persona_profile,
                    s.route_mode,
                    s.created_at,
                    s.updated_at,
                    COUNT(m.id) AS message_count
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def get_session_messages(session_id: str, limit: int = 300) -> list[dict[str, Any]]:
    with DB_LOCK:
        conn = get_db_conn()
        try:
            rows = conn.execute(
                """
                SELECT role, content, provider, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def delete_session(session_id: str) -> None:
    with DB_LOCK:
        conn = get_db_conn()
        try:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()


def get_profiles() -> dict[str, str]:
    profiles = CONFIG.get("profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        return {
            "open_source_architect": "You prioritize open-source-first technical solutions.",
        }
    return profiles


def build_messages(
    user_message: str,
    history: list[dict[str, str]],
    persona_profile: str,
) -> list[dict[str, str]]:
    system_base = CONFIG.get("system_prompt", "You are Infinity-Chat, a practical AI assistant.")
    profile_block = get_profiles().get(
        persona_profile,
        "Respond with practical and reliable engineering guidance.",
    )
    system_prompt = f"{system_base}\n\nActive profile: {persona_profile}\n{profile_block}"

    trimmed = history[-MAX_HISTORY_MESSAGES:]
    messages = [{"role": "system", "content": system_prompt}]

    for msg in trimmed:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in {"system", "user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})
    return messages


def get_provider_map() -> dict[str, Provider]:
    return {
        "groq": Provider(
            name="groq",
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=os.getenv("GROQ_API_KEY"),
            model=os.getenv("GROQ_MODEL", CONFIG.get("groq_model", "llama-4-70b")),
        ),
        "openrouter": Provider(
            name="openrouter",
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=os.getenv(
                "OPENROUTER_MODEL",
                CONFIG.get("openrouter_model", "mistral-small-3.1-24b-instruct:free"),
            ),
        ),
    }


def pick_provider_order(request: ChatRequest) -> list[Provider]:
    provider_map = get_provider_map()

    if request.force_provider in provider_map:
        return [provider_map[request.force_provider]]

    mode = (request.route_mode or DEFAULT_ROUTE_MODE).lower()
    has_code_intent = any(
        kw in request.message.lower()
        for kw in ["code", "debug", "stacktrace", "python", "fastapi", "streamlit"]
    )

    if mode == "speed":
        order = ["groq", "openrouter"]
    elif mode == "economy":
        order = ["openrouter", "groq"]
    else:
        order = ["groq", "openrouter"] if has_code_intent else ["openrouter", "groq"]

    return [provider_map[name] for name in order]


def sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=True)
    return f"event: {event}\ndata: {payload}\n\n"


async def stream_from_provider(
    provider: Provider,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> AsyncGenerator[str, None]:
    if not provider.api_key:
        raise NonRetryableProviderError(f"Missing API key for provider: {provider.name}")

    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }

    if provider.name == "openrouter":
        headers["HTTP-Referer"] = os.getenv("OPENROUTER_REFERER", "http://localhost:8501")
        headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME", "Infinity-Chat")

    payload = {
        "model": provider.model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    timeout = httpx.Timeout(connect=15.0, read=None, write=30.0, pool=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{provider.base_url}/chat/completions",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status_code == 429 or resp.status_code >= 500:
                body = await resp.aread()
                raise RetryableProviderError(
                    f"{provider.name} returned {resp.status_code}: {body[:300].decode(errors='ignore')}"
                )

            if resp.status_code >= 400:
                body = await resp.aread()
                raise NonRetryableProviderError(
                    f"{provider.name} returned {resp.status_code}: {body[:300].decode(errors='ignore')}"
                )

            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue

                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                token = delta.get("content")
                if token:
                    yield token


def metrics_snapshot() -> dict[str, Any]:
    with DB_LOCK:
        conn = get_db_conn()
        try:
            total = conn.execute("SELECT COUNT(*) AS c FROM request_logs").fetchone()["c"]
            success = conn.execute(
                "SELECT COUNT(*) AS c FROM request_logs WHERE status = 'ok'"
            ).fetchone()["c"]
            fallback_count = conn.execute(
                "SELECT COUNT(*) AS c FROM request_logs WHERE fallback_used = 1"
            ).fetchone()["c"]
            avg_latency = conn.execute(
                "SELECT COALESCE(AVG(latency_ms), 0) AS a FROM request_logs"
            ).fetchone()["a"]
            provider_rows = conn.execute(
                "SELECT provider, COUNT(*) AS c FROM request_logs GROUP BY provider"
            ).fetchall()
            recent_rows = conn.execute(
                """
                SELECT request_id, session_id, provider, status, fallback_used, latency_ms, error, created_at
                FROM request_logs
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()
        finally:
            conn.close()

    provider_counts = {row["provider"]: row["c"] for row in provider_rows}
    return {
        "window_size": REQUEST_LOG.maxlen,
        "total_requests": total,
        "success_requests": success,
        "failure_requests": total - success,
        "fallback_count": fallback_count,
        "avg_latency_ms": round(float(avg_latency or 0.0), 2),
        "provider_counts": provider_counts,
        "recent": [dict(row) for row in recent_rows],
    }


@app.on_event("startup")
async def on_startup() -> None:
    init_db()


@app.get("/health")
async def health() -> dict[str, Any]:
    provider_map = get_provider_map()
    return {
        "status": "ok",
        "version": "2.1.0",
        "providers": [
            {
                "name": p.name,
                "configured": bool(p.api_key),
                "model": p.model,
            }
            for p in provider_map.values()
        ],
    }


@app.get("/storage/info")
async def storage_info() -> dict[str, Any]:
    size_bytes = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    return {
        "db_path": str(DB_PATH.resolve()),
        "exists": DB_PATH.exists(),
        "size_bytes": size_bytes,
    }


@app.get("/profiles")
async def profiles() -> dict[str, Any]:
    return {
        "default_route_mode": DEFAULT_ROUTE_MODE,
        "profiles": get_profiles(),
    }


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    return metrics_snapshot()


@app.get("/sessions")
async def sessions(limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 200))
    return {"sessions": list_sessions(safe_limit)}


@app.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str, limit: int = 300) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 1000))
    return {"session_id": session_id, "messages": get_session_messages(session_id, safe_limit)}


@app.delete("/sessions/{session_id}")
async def remove_session(session_id: str) -> dict[str, Any]:
    delete_session(session_id)
    return {"deleted": True, "session_id": session_id}


@app.post("/chat")
async def chat(request: ChatRequest) -> JSONResponse:
    session_id = request.session_id or str(uuid.uuid4())
    route_mode = request.route_mode or DEFAULT_ROUTE_MODE
    messages = build_messages(request.message, request.history, request.persona_profile)
    providers = pick_provider_order(request)

    ensure_session(session_id, request.message, request.persona_profile, route_mode)
    save_chat_message(session_id, "user", request.message)

    content_parts: list[str] = []
    started_at = time.perf_counter()
    fallback_used = False

    for idx, provider in enumerate(providers):
        try:
            async for token in stream_from_provider(
                provider,
                messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                content_parts.append(token)

            assistant_content = "".join(content_parts)
            save_chat_message(session_id, "assistant", assistant_content, provider=provider.name)

            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            persist_request_log(
                {
                    "request_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "provider": provider.name,
                    "status": "ok",
                    "fallback_used": fallback_used,
                    "latency_ms": latency_ms,
                }
            )
            return JSONResponse(
                {
                    "session_id": session_id,
                    "provider": provider.name,
                    "content": assistant_content,
                    "fallback_used": fallback_used,
                    "latency_ms": latency_ms,
                }
            )
        except RetryableProviderError:
            fallback_used = fallback_used or idx == 0
            continue
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            persist_request_log(
                {
                    "request_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "provider": provider.name,
                    "status": "error",
                    "fallback_used": fallback_used,
                    "latency_ms": latency_ms,
                    "error": str(exc),
                }
            )
            return JSONResponse({"error": str(exc), "session_id": session_id}, status_code=500)

    if OFFLINE_FALLBACK_ENABLED:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        fallback_text = (
            "All online providers were unavailable. "
            "Offline fallback mode is active. Please retry in a minute or check API limits."
        )
        save_chat_message(session_id, "assistant", fallback_text, provider="offline")
        persist_request_log(
            {
                "request_id": str(uuid.uuid4()),
                "session_id": session_id,
                "provider": "offline",
                "status": "ok",
                "fallback_used": True,
                "latency_ms": latency_ms,
            }
        )
        return JSONResponse(
            {
                "session_id": session_id,
                "provider": "offline",
                "content": fallback_text,
                "fallback_used": True,
                "latency_ms": latency_ms,
            }
        )

    return JSONResponse({"error": "All providers failed", "session_id": session_id}, status_code=503)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    request_id = str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())
    route_mode = request.route_mode or DEFAULT_ROUTE_MODE

    messages = build_messages(request.message, request.history, request.persona_profile)
    providers = pick_provider_order(request)

    ensure_session(session_id, request.message, request.persona_profile, route_mode)
    save_chat_message(session_id, "user", request.message)

    async def event_generator() -> AsyncGenerator[str, None]:
        started_at = time.perf_counter()
        token_count = 0
        fallback_used = False
        assistant_parts: list[str] = []

        yield sse(
            "meta",
            {
                "request_id": request_id,
                "session_id": session_id,
                "route_mode": request.route_mode,
                "persona_profile": request.persona_profile,
                "providers": [p.name for p in providers],
            },
        )

        for idx, provider in enumerate(providers):
            try:
                yield sse("status", {"provider": provider.name, "message": "starting"})
                async for token in stream_from_provider(
                    provider,
                    messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                ):
                    token_count += 1
                    assistant_parts.append(token)
                    yield sse("token", {"provider": provider.name, "text": token})

                assistant_text = "".join(assistant_parts)
                save_chat_message(session_id, "assistant", assistant_text, provider=provider.name)

                latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                persist_request_log(
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "provider": provider.name,
                        "status": "ok",
                        "fallback_used": fallback_used,
                        "latency_ms": latency_ms,
                        "token_events": token_count,
                    }
                )
                yield sse(
                    "done",
                    {
                        "provider": provider.name,
                        "request_id": request_id,
                        "session_id": session_id,
                        "fallback_used": fallback_used,
                        "latency_ms": latency_ms,
                        "token_events": token_count,
                    },
                )
                return
            except RetryableProviderError as exc:
                is_last = idx == len(providers) - 1
                fallback_used = True
                if is_last:
                    if OFFLINE_FALLBACK_ENABLED:
                        offline_text = (
                            "All providers were unavailable, so offline fallback mode answered. "
                            "Please retry shortly or verify API keys and limits."
                        )
                        for piece in offline_text.split(" "):
                            token_count += 1
                            assistant_parts.append(piece + " ")
                            yield sse("token", {"provider": "offline", "text": piece + " "})

                        assistant_text = "".join(assistant_parts)
                        save_chat_message(session_id, "assistant", assistant_text, provider="offline")

                        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                        persist_request_log(
                            {
                                "request_id": request_id,
                                "session_id": session_id,
                                "provider": "offline",
                                "status": "ok",
                                "fallback_used": True,
                                "latency_ms": latency_ms,
                                "token_events": token_count,
                            }
                        )
                        yield sse(
                            "done",
                            {
                                "provider": "offline",
                                "request_id": request_id,
                                "session_id": session_id,
                                "fallback_used": True,
                                "latency_ms": latency_ms,
                                "token_events": token_count,
                            },
                        )
                        return

                    yield sse("error", {"message": str(exc), "final": True})
                    return

                yield sse(
                    "status",
                    {
                        "provider": provider.name,
                        "message": "rate_limited_or_server_error_fallback",
                        "detail": str(exc),
                    },
                )
            except NonRetryableProviderError as exc:
                latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                persist_request_log(
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "provider": provider.name,
                        "status": "error",
                        "fallback_used": fallback_used,
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    }
                )
                yield sse("error", {"message": str(exc), "final": True})
                return
            except Exception as exc:  # noqa: BLE001
                latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                persist_request_log(
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "provider": provider.name,
                        "status": "error",
                        "fallback_used": fallback_used,
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    }
                )
                yield sse(
                    "error",
                    {
                        "message": f"Unexpected error from {provider.name}: {exc}",
                        "final": True,
                    },
                )
                return

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
