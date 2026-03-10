import json
import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8080")
MAX_LOCAL_MEMORY = int(os.getenv("MAX_LOCAL_MEMORY", "10"))

st.set_page_config(page_title="Infinity-Chat", page_icon="infinity", layout="wide")
st.title("Infinity-Chat")
st.caption("Groq primary + OpenRouter free-tier fallback with live streaming")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hello. I am Infinity-Chat. Ask anything about open-source AI, coding, or systems.",
        }
    ]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Message Infinity-Chat...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        status_placeholder = st.empty()
        full_answer = ""

        payload = {
            "message": prompt,
            "history": st.session_state.messages[-MAX_LOCAL_MEMORY:],
            "session_id": "streamlit-local",
        }

        event_type = None
        try:
            with requests.post(
                f"{BACKEND_URL}/chat/stream",
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
                                payload = json.loads(body)
                            except json.JSONDecodeError:
                                continue

                            if event_type == "status":
                                provider = payload.get("provider", "unknown")
                                msg = payload.get("message", "")
                                status_placeholder.caption(f"Provider: {provider} | Status: {msg}")
                            elif event_type == "token":
                                token = payload.get("text", "")
                                full_answer += token
                                answer_placeholder.markdown(full_answer)
                            elif event_type == "error":
                                status_placeholder.error(payload.get("message", "Unknown error"))
                            elif event_type == "done":
                                provider = payload.get("provider", "unknown")
                                status_placeholder.caption(f"Completed via {provider}")
        except requests.RequestException as exc:
            status_placeholder.error(f"Connection failed: {exc}")

    final_answer = full_answer or "No response received."
    st.session_state.messages.append({"role": "assistant", "content": final_answer})

    # Keep only last 10 conversation messages + initial assistant greeting if present.
    if len(st.session_state.messages) > MAX_LOCAL_MEMORY + 1:
        greeting = st.session_state.messages[0]
        tail = st.session_state.messages[-MAX_LOCAL_MEMORY:]
        if greeting.get("role") == "assistant":
            st.session_state.messages = [greeting] + tail
        else:
            st.session_state.messages = tail
