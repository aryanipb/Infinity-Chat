import json
import os
import socket
import uuid
from datetime import datetime

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL_DEFAULT = os.getenv("BACKEND_URL", "http://127.0.0.1:8080")
MAX_LOCAL_MEMORY_DEFAULT = int(os.getenv("MAX_LOCAL_MEMORY", "10"))


def get_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def fetch_profiles(backend_url: str) -> dict[str, str]:
    try:
        response = requests.get(f"{backend_url}/profiles", timeout=8)
        if response.status_code == 200:
            return response.json().get("profiles", {})
    except requests.RequestException:
        pass
    return {
        "open_source_architect": "Prioritizes open-source-first solutions.",
        "rapid_prototyper": "Optimizes for fastest implementation path.",
    }


def fetch_sessions(backend_url: str) -> list[dict]:
    try:
        response = requests.get(f"{backend_url}/sessions", params={"limit": 100}, timeout=8)
        if response.status_code == 200:
            return response.json().get("sessions", [])
    except requests.RequestException:
        pass
    return []


def fetch_session_messages(backend_url: str, session_id: str) -> list[dict]:
    try:
        response = requests.get(
            f"{backend_url}/sessions/{session_id}/messages",
            params={"limit": 1000},
            timeout=12,
        )
        if response.status_code == 200:
            rows = response.json().get("messages", [])
            return [{"role": row.get("role", "assistant"), "content": row.get("content", "")} for row in rows]
    except requests.RequestException:
        pass
    return []


def delete_session(backend_url: str, session_id: str) -> bool:
    try:
        response = requests.delete(f"{backend_url}/sessions/{session_id}", timeout=8)
        return response.status_code == 200
    except requests.RequestException:
        return False


def storage_info(backend_url: str) -> dict:
    try:
        response = requests.get(f"{backend_url}/storage/info", timeout=8)
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        pass
    return {"db_path": "unavailable", "exists": False, "size_bytes": 0}


def export_markdown(messages: list[dict[str, str]]) -> str:
    lines = ["# Infinity-Chat Conversation", ""]
    lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
    lines.append("")
    for item in messages:
        role = item.get("role", "unknown").upper()
        content = item.get("content", "")
        lines.append(f"## {role}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def load_health(backend_url: str) -> dict:
    try:
        response = requests.get(f"{backend_url}/health", timeout=8)
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        pass
    return {"status": "unreachable", "providers": []}


def load_metrics(backend_url: str) -> dict:
    try:
        response = requests.get(f"{backend_url}/metrics", timeout=8)
        if response.status_code == 200:
            return response.json()
    except requests.RequestException:
        pass
    return {
        "total_requests": 0,
        "success_requests": 0,
        "fallback_count": 0,
        "avg_latency_ms": 0,
        "provider_counts": {},
        "recent": [],
    }


st.set_page_config(page_title="Infinity-Chat", page_icon="infinity", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
      background: radial-gradient(circle at 10% 20%, #101726 0%, #0b0f19 45%, #07090f 100%);
      color: #f5f7ff;
    }
    .block-container {max-width: 1100px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Infinity-Chat Control Console")
st.caption("Adaptive routing, persistent sessions, live failover telemetry")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Welcome to Infinity-Chat v2. Persistent local storage is enabled via SQLite. "
                "Your chats are stored on disk and can be reloaded."
            ),
        }
    ]

if "backend_url" not in st.session_state:
    st.session_state.backend_url = BACKEND_URL_DEFAULT
if "max_local_memory" not in st.session_state:
    st.session_state.max_local_memory = MAX_LOCAL_MEMORY_DEFAULT
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

with st.sidebar:
    st.subheader("Runtime")
    backend_url = st.text_input("Backend URL", value=st.session_state.backend_url)
    st.session_state.backend_url = backend_url.rstrip("/")

    route_mode = st.selectbox("Route mode", ["balanced", "speed", "economy"], index=0)
    force_provider = st.selectbox("Force provider", ["auto", "groq", "openrouter"], index=0)
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.5, value=0.7, step=0.1)
    max_tokens = st.slider("Max tokens", min_value=128, max_value=4096, value=1024, step=128)
    st.session_state.max_local_memory = st.slider(
        "Local memory (messages)",
        min_value=6,
        max_value=30,
        value=st.session_state.max_local_memory,
        step=2,
    )

    profiles = fetch_profiles(st.session_state.backend_url)
    profile_keys = list(profiles.keys())
    default_profile = "open_source_architect" if "open_source_architect" in profiles else profile_keys[0]
    persona_profile = st.selectbox(
        "Persona profile",
        profile_keys,
        index=profile_keys.index(default_profile),
    )

    st.subheader("Persistence")
    st.caption(f"Current session: `{st.session_state.session_id}`")

    store = storage_info(st.session_state.backend_url)
    st.caption(f"DB: `{store.get('db_path', 'unknown')}`")
    st.caption(f"DB size: {store.get('size_bytes', 0)} bytes")

    sessions = fetch_sessions(st.session_state.backend_url)
    session_labels = [
        f"{row.get('title', 'Untitled')} | {row.get('session_id', '')[:8]} | {row.get('message_count', 0)} msgs"
        for row in sessions
    ]
    session_index = st.selectbox(
        "Saved sessions",
        options=list(range(len(session_labels))) if session_labels else [0],
        format_func=lambda idx: session_labels[idx] if session_labels else "No saved sessions",
    )

    col_new, col_load = st.columns(2)
    if col_new.button("New", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = [{"role": "assistant", "content": "New persistent session started."}]

    if col_load.button("Load", use_container_width=True) and sessions:
        selected = sessions[session_index]
        loaded_messages = fetch_session_messages(st.session_state.backend_url, selected["session_id"])
        if loaded_messages:
            st.session_state.session_id = selected["session_id"]
            st.session_state.messages = loaded_messages
            st.success("Session loaded")

    if st.button("Delete Selected Session", use_container_width=True) and sessions:
        selected = sessions[session_index]
        if delete_session(st.session_state.backend_url, selected["session_id"]):
            st.success("Session deleted")
            if st.session_state.session_id == selected["session_id"]:
                st.session_state.session_id = str(uuid.uuid4())
                st.session_state.messages = [{"role": "assistant", "content": "Session deleted. New session started."}]

    st.subheader("Session Tools")
    md_data = export_markdown(st.session_state.messages)
    st.download_button(
        label="Export Markdown",
        data=md_data,
        file_name="infinity_chat_conversation.md",
        mime="text/markdown",
        use_container_width=True,
    )

    json_data = json.dumps(st.session_state.messages, indent=2)
    st.download_button(
        label="Export JSON",
        data=json_data,
        file_name="infinity_chat_conversation.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded = st.file_uploader("Import JSON chat", type=["json"])
    if uploaded is not None:
        try:
            loaded = json.loads(uploaded.read().decode("utf-8"))
            if isinstance(loaded, list):
                st.session_state.messages = loaded
                st.success("Conversation imported")
            else:
                st.error("JSON must be a list of {role, content} messages")
        except json.JSONDecodeError:
            st.error("Invalid JSON file")

    st.subheader("Network")
    lan_ip = get_lan_ip()
    st.code(f"Desktop URL: http://127.0.0.1:8501\nLAN URL: http://{lan_ip}:8501", language="text")
    st.caption("Android access: connect phone to same Wi-Fi and open LAN URL in browser.")

health = load_health(st.session_state.backend_url)
metrics = load_metrics(st.session_state.backend_url)

col1, col2, col3, col4 = st.columns(4)
col1.metric("API Status", health.get("status", "unknown"))
col2.metric("Requests", metrics.get("total_requests", 0))
col3.metric("Fallbacks", metrics.get("fallback_count", 0))
col4.metric("Avg Latency (ms)", metrics.get("avg_latency_ms", 0))

providers = health.get("providers", [])
if providers:
    st.markdown("### Provider Matrix")
    st.dataframe(providers, use_container_width=True)

st.markdown("### Prompt Presets")
chip_col1, chip_col2, chip_col3 = st.columns(3)
if chip_col1.button("Code Review Request", use_container_width=True):
    st.session_state["preset_prompt"] = "Review this code for bugs, regressions, and missing tests."
if chip_col2.button("Architecture Plan", use_container_width=True):
    st.session_state["preset_prompt"] = "Design a scalable architecture with tradeoffs and rollout plan."
if chip_col3.button("Debug Session", use_container_width=True):
    st.session_state["preset_prompt"] = "Help me debug this error step-by-step with hypotheses and checks."

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

preset = st.session_state.get("preset_prompt", "")
prompt = st.chat_input("Message Infinity-Chat...", key="chat_input")
if not prompt and preset:
    prompt = preset
    st.session_state["preset_prompt"] = ""

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        status_placeholder = st.empty()
        debug_placeholder = st.empty()
        full_answer = ""
        debug_lines: list[str] = []

        payload = {
            "message": prompt,
            "history": st.session_state.messages[-st.session_state.max_local_memory :],
            "session_id": st.session_state.session_id,
            "persona_profile": persona_profile,
            "route_mode": route_mode,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "force_provider": None if force_provider == "auto" else force_provider,
        }

        event_type = None
        try:
            with requests.post(
                f"{st.session_state.backend_url}/chat/stream",
                json=payload,
                stream=True,
                timeout=300,
            ) as resp:
                if resp.status_code >= 400:
                    st.error(f"Backend error {resp.status_code}: {resp.text[:300]}")
                else:
                    for raw_line in resp.iter_lines(decode_unicode=True):
                        if raw_line is None:
                            continue

                        line = raw_line.strip()
                        if not line:
                            continue

                        if line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                            continue

                        if line.startswith("data:"):
                            body = line.split(":", 1)[1].strip()
                            try:
                                packet = json.loads(body)
                            except json.JSONDecodeError:
                                continue

                            if event_type == "meta":
                                providers_text = " -> ".join(packet.get("providers", []))
                                st.session_state.session_id = packet.get("session_id", st.session_state.session_id)
                                status_placeholder.caption(
                                    f"Req {packet.get('request_id', '-')[:8]} | Session: {st.session_state.session_id[:8]} "
                                    f"| Mode: {packet.get('route_mode')} | Profile: {packet.get('persona_profile')} "
                                    f"| Plan: {providers_text}"
                                )
                            elif event_type == "status":
                                provider = packet.get("provider", "unknown")
                                msg = packet.get("message", "")
                                detail = packet.get("detail", "")
                                line_text = f"[{provider}] {msg}"
                                if detail:
                                    line_text += f" | {detail[:120]}"
                                debug_lines.append(line_text)
                                debug_placeholder.code("\n".join(debug_lines[-6:]), language="text")
                            elif event_type == "token":
                                token = packet.get("text", "")
                                full_answer += token
                                answer_placeholder.markdown(full_answer)
                            elif event_type == "error":
                                status_placeholder.error(packet.get("message", "Unknown error"))
                            elif event_type == "done":
                                provider = packet.get("provider", "unknown")
                                latency = packet.get("latency_ms", "?")
                                fallback = packet.get("fallback_used", False)
                                status_placeholder.caption(
                                    f"Completed via {provider} | latency {latency} ms | fallback={fallback}"
                                )
        except requests.RequestException as exc:
            status_placeholder.error(f"Connection failed: {exc}")

    final_answer = full_answer or "No response received."
    st.session_state.messages.append({"role": "assistant", "content": final_answer})

    if len(st.session_state.messages) > st.session_state.max_local_memory + 1:
        greeting = st.session_state.messages[0]
        tail = st.session_state.messages[-st.session_state.max_local_memory :]
        if greeting.get("role") == "assistant":
            st.session_state.messages = [greeting] + tail
        else:
            st.session_state.messages = tail
