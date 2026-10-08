"""
Streamlit Frontend for AI DevOps Incident Response Agent.
Integrates directly with the existing LangGraph agent, RAG pipeline, and tool registry.
"""
import os
import sys
import uuid
from pathlib import Path

import streamlit as st

# Ensure Backend package is in Python path
BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "Backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Import existing application logic
from app.agent.graph import run_graph
from app.file_handler import process_upload
from app.rag.rag import list_sources

# ------------------------------------------------------------------ PAGE CONFIG
st.set_page_config(
    page_title="AI DevOps Incident Response Agent",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished UI
st.markdown("""
<style>
    .stApp {
        max-width: 1250px;
        margin: 0 auto;
    }
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #ff4b4b;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #a0aab8;
        margin-bottom: 1.5rem;
    }
    .tool-tag {
        display: inline-block;
        background-color: #1e293b;
        color: #38bdf8;
        border: 1px solid #0284c7;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 6px;
        margin-top: 6px;
    }
    .file-badge {
        font-size: 0.85rem;
        padding: 4px 8px;
        border-radius: 4px;
        margin-bottom: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ SESSION STATE
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []


# ------------------------------------------------------------------ SIDEBAR
with st.sidebar:
    st.title("⚙️ Control Panel")
    
    # 1. Groq API Key Config
    env_key = os.getenv("GROQ_API_KEY", "")
    if not env_key:
        api_key_input = st.text_input(
            "GROQ API Key",
            type="password",
            help="Enter your Groq API key (starts with gsk_)"
        )
        if api_key_input:
            os.environ["GROQ_API_KEY"] = api_key_input
            st.success("API Key saved for current session!")
    else:
        st.success("✅ GROQ_API_KEY loaded from environment")

    st.divider()

    # 2. Document & Evidence File Upload
    st.subheader("📁 Upload Evidence / Runbooks")
    st.caption("Upload `.pdf`, `.md`, `.log`, `.csv`, `.json`, or `.txt` files.")

    uploaded_files = st.file_uploader(
        "Choose file(s)",
        type=["pdf", "md", "markdown", "rst", "log", "txt", "out", "jsonl", "csv", "json"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        for file in uploaded_files:
            file_key = f"{file.name}_{file.size}"
            if file_key not in st.session_state.uploaded_files:
                data = file.read()
                if not data:
                    st.error(f"File '{file.name}' is empty.")
                    continue
                try:
                    with st.spinner(f"Ingesting {file.name}..."):
                        res = process_upload(
                            st.session_state.user_id,
                            st.session_state.conversation_id,
                            file.name,
                            data,
                        )
                        st.session_state.uploaded_files.append(file_key)
                        st.toast(f"Uploaded {file.name}: {res.get('detail', 'success')}")
                except Exception as e:
                    st.error(f"Failed to process '{file.name}': {e}")

    # 3. Active Session Files List
    st.divider()
    st.subheader("📚 Active Evidence & Documents")

    # Fetch indexed RAG sources
    try:
        rag_docs = list_sources(st.session_state.user_id)
        if rag_docs:
            st.markdown("**Indexed Runbooks / Docs:**")
            for doc in rag_docs:
                st.markdown(f"📄 `{doc}`")
        else:
            st.caption("No RAG documents indexed yet.")
    except Exception:
        st.caption("No RAG documents indexed yet.")

    st.divider()

    # 4. Session Actions
    if st.button("🔄 Start New Incident Session", use_container_width=True):
        st.session_state.conversation_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.uploaded_files = []
        st.rerun()


# ------------------------------------------------------------------ MAIN CHAT
st.markdown('<div class="main-title">🚨 AI DevOps Incident Response Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Automated incident investigation, root cause correlation, RAG runbook lookup, log analysis & metric trends</div>',
    unsafe_allow_html=True,
)

# Display Chat Messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tools_used"):
            st.markdown(
                " ".join([f'<span class="tool-tag">🔧 {t}</span>' for t in msg["tools_used"]]),
                unsafe_allow_html=True,
            )

# Chat Input & AI Response
prompt = st.chat_input("Describe the incident (e.g. 'Why is API latency spiking after deployment?')")

if prompt:
    # Check for API key before processing
    if not os.getenv("GROQ_API_KEY"):
        st.error("⚠️ GROQ_API_KEY is missing! Please enter your Groq API Key in the sidebar or set it in your environment.")
        st.stop()

    # Add user message to UI
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Format history for graph (OpenAI role format)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
    ]

    with st.chat_message("assistant"):
        with st.spinner("🔍 Investigating incident, correlating metrics, analyzing logs & checking runbooks..."):
            try:
                res = run_graph(
                    prompt,
                    history,
                    st.session_state.user_id,
                    st.session_state.conversation_id,
                )
                answer = res.get("answer", "No answer generated.")
                tools_used = res.get("tools_used", [])

                st.markdown(answer)

                if tools_used:
                    st.markdown(
                        " ".join([f'<span class="tool-tag">🔧 {t}</span>' for t in tools_used]),
                        unsafe_allow_html=True,
                    )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "tools_used": tools_used,
                    }
                )
            except Exception as e:
                error_msg = f"❌ Incident Investigation Error: {e}"
                st.error(error_msg)
                st.session_state.messages.append(
                    {"role": "assistant", "content": error_msg}
                )
