import json
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, AsyncGenerator

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, StreamingResponse

load_dotenv()


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

app = FastAPI(title="Infinity-Chat API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def record_metric(entry: dict[str, Any]) -> None:
    REQUEST_LOG.append(entry)


def metrics_snapshot() -> dict[str, Any]:
    total = len(REQUEST_LOG)
    success = sum(1 for row in REQUEST_LOG if row.get("status") == "ok")
    fallback_count = sum(1 for row in REQUEST_LOG if row.get("fallback_used"))
    provider_counts: dict[str, int] = {"groq": 0, "openrouter": 0, "offline": 0}
    total_latency = 0.0

    for row in REQUEST_LOG:
        provider = row.get("provider", "offline")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        total_latency += float(row.get("latency_ms", 0.0))

    avg_latency = round(total_latency / total, 2) if total else 0.0

    return {
        "window_size": REQUEST_LOG.maxlen,
        "total_requests": total,
        "success_requests": success,
        "failure_requests": total - success,
        "fallback_count": fallback_count,
        "avg_latency_ms": avg_latency,
        "provider_counts": provider_counts,
        "recent": list(REQUEST_LOG)[-10:],
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    provider_map = get_provider_map()
    return {
        "status": "ok",
        "version": "2.0.0",
        "providers": [
            {
                "name": p.name,
                "configured": bool(p.api_key),
                "model": p.model,
            }
            for p in provider_map.values()
        ],
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


@app.post("/chat")
async def chat(request: ChatRequest) -> JSONResponse:
    messages = build_messages(request.message, request.history, request.persona_profile)
    providers = pick_provider_order(request)

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

            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            record_metric(
                {
                    "request_id": str(uuid.uuid4()),
                    "provider": provider.name,
                    "status": "ok",
                    "fallback_used": fallback_used,
                    "latency_ms": latency_ms,
                }
            )
            return JSONResponse(
                {
                    "provider": provider.name,
                    "content": "".join(content_parts),
                    "fallback_used": fallback_used,
                    "latency_ms": latency_ms,
                }
            )
        except RetryableProviderError:
            fallback_used = fallback_used or idx == 0
            continue
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            record_metric(
                {
                    "request_id": str(uuid.uuid4()),
                    "provider": provider.name,
                    "status": "error",
                    "fallback_used": fallback_used,
                    "latency_ms": latency_ms,
                    "error": str(exc),
                }
            )
            return JSONResponse({"error": str(exc)}, status_code=500)

    if OFFLINE_FALLBACK_ENABLED:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        fallback_text = (
            "All online providers were unavailable. "
            "Offline fallback mode is active. Please retry in a minute or check API limits."
        )
        record_metric(
            {
                "request_id": str(uuid.uuid4()),
                "provider": "offline",
                "status": "ok",
                "fallback_used": True,
                "latency_ms": latency_ms,
            }
        )
        return JSONResponse(
            {
                "provider": "offline",
                "content": fallback_text,
                "fallback_used": True,
                "latency_ms": latency_ms,
            }
        )

    return JSONResponse({"error": "All providers failed"}, status_code=503)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    request_id = str(uuid.uuid4())
    messages = build_messages(request.message, request.history, request.persona_profile)
    providers = pick_provider_order(request)

    async def event_generator() -> AsyncGenerator[str, None]:
        started_at = time.perf_counter()
        token_count = 0
        fallback_used = False

        yield sse(
            "meta",
            {
                "request_id": request_id,
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
                    yield sse("token", {"provider": provider.name, "text": token})

                latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                record_metric(
                    {
                        "request_id": request_id,
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
                            yield sse("token", {"provider": "offline", "text": piece + " "})

                        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                        record_metric(
                            {
                                "request_id": request_id,
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
                record_metric(
                    {
                        "request_id": request_id,
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
                record_metric(
                    {
                        "request_id": request_id,
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
