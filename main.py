import json
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

load_dotenv()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    session_id: str | None = None


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
            "groq_model": "llama-4-70b",
            "openrouter_model": "mistral-small-3.1-24b-instruct:free",
        }

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


CONFIG = load_config(os.getenv("CONFIG_PATH", "config.yaml"))
SYSTEM_PROMPT = CONFIG.get("system_prompt", "You are Infinity-Chat, a practical AI assistant.")
MAX_HISTORY_MESSAGES = int(CONFIG.get("max_history_messages", 10))

app = FastAPI(title="Infinity-Chat API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_messages(user_message: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for msg in trimmed:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in {"system", "user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})
    return messages


def get_providers() -> list[Provider]:
    return [
        Provider(
            name="groq",
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=os.getenv("GROQ_API_KEY"),
            model=os.getenv("GROQ_MODEL", CONFIG.get("groq_model", "llama-4-70b")),
        ),
        Provider(
            name="openrouter",
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=os.getenv(
                "OPENROUTER_MODEL",
                CONFIG.get("openrouter_model", "mistral-small-3.1-24b-instruct:free"),
            ),
        ),
    ]


def sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=True)
    return f"event: {event}\ndata: {payload}\n\n"


async def stream_from_provider(
    provider: Provider,
    messages: list[dict[str, str]],
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
        "temperature": 0.7,
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


@app.get("/health")
async def health() -> dict[str, Any]:
    providers = get_providers()
    return {
        "status": "ok",
        "providers": [
            {"name": p.name, "configured": bool(p.api_key), "model": p.model} for p in providers
        ],
    }


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    messages = build_messages(request.message, request.history)
    providers = get_providers()

    async def event_generator() -> AsyncGenerator[str, None]:
        for idx, provider in enumerate(providers):
            try:
                yield sse("status", {"provider": provider.name, "message": "starting"})
                async for token in stream_from_provider(provider, messages):
                    yield sse("token", {"provider": provider.name, "text": token})
                yield sse("done", {"provider": provider.name})
                return
            except RetryableProviderError as exc:
                is_last = idx == len(providers) - 1
                if is_last:
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
                yield sse("error", {"message": str(exc), "final": True})
                return
            except Exception as exc:  # noqa: BLE001
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
