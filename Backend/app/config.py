"""Central configuration: paths, model names and secrets."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Backend/ folder (works no matter where you start uvicorn from)
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
USERS_DIR = DATA_DIR / "users"       # data/users/<user_id>/<conversation_id>/{logs,metrics}
QDRANT_PATH = BASE_DIR / "qdrant_storage"

# v2: chunks now carry a user_id. A new name keeps old chunks (without user_id) out of the way.
COLLECTION_NAME = "devops_documents_v2"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

MAX_UPLOAD_MB = 25
MAX_TOOL_CHARS = 6000   # tool output is truncated to protect the LLM context
MAX_TOOL_ROUNDS = 6     # max investigation rounds before forcing a final answer

USERS_DIR.mkdir(parents=True, exist_ok=True)


def conversation_dir(user_id: str, conversation_id: str) -> Path:
    """Folder holding the logs/metrics of ONE conversation of ONE user."""
    return USERS_DIR / str(user_id) / str(conversation_id)