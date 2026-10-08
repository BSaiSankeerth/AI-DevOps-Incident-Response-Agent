import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg2.errors
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import db
from app.agent.graph import run_graph
from app.auth import create_token, get_current_user, hash_password, verify_password
from app.config import MAX_UPLOAD_MB, USERS_DIR, conversation_dir
from app.file_handler import process_upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        db.check_schema()
    except Exception as e:
        raise RuntimeError(
            f"PostgreSQL is not ready: {e}\n"
            "Check DATABASE_URL in Backend/.env and run schema.sql once."
        ) from e
    yield


app = FastAPI(
    title="AI DevOps Incident Response Agent",
    description="AI-powered DevOps incident analysis and response system",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ models
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=6, max_length=72)
    email: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _own_conversation(user: dict, conversation_id: uuid.UUID) -> dict:
    """404 unless the conversation exists AND belongs to the logged-in user."""
    conv = db.get_conversation(user["id"], str(conversation_id))
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    return conv


# ------------------------------------------------------------------ basic
@app.get("/")
def root():
    return {"message": "AI DevOps Incident Response Agent is running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# ------------------------------------------------------------------ auth
@app.post("/auth/register", status_code=201)
def register(req: RegisterRequest):
    if len(req.password.encode("utf-8")) > 72:
        raise HTTPException(400, "Password is too long (max 72 bytes).")
    username = req.username.strip().lower()
    email = (req.email or "").strip().lower() or None
    try:
        user = db.create_user(username, hash_password(req.password), email)
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(409, "That username or email is already registered.")
    return {"access_token": create_token(user["id"]), "token_type": "bearer", "user": user}


@app.post("/auth/login")
def login(req: LoginRequest):
    user = db.get_user_by_username(req.username.strip().lower())
    if user is None or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid username or password.")
    return {
        "access_token": create_token(user["id"]),
        "token_type": "bearer",
        "user": {"id": user["id"], "username": user["username"]},
    }


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return user


# ------------------------------------------------------------------ conversations
@app.get("/conversations")
def list_conversations(user: dict = Depends(get_current_user)):
    return db.list_conversations(user["id"])


@app.post("/conversations", status_code=201)
def create_conversation(user: dict = Depends(get_current_user)):
    return db.create_conversation(user["id"])


@app.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: uuid.UUID, req: RenameRequest, user: dict = Depends(get_current_user)):
    _own_conversation(user, conversation_id)
    db.rename_conversation(user["id"], str(conversation_id), req.title.strip())
    return {"message": "Renamed."}


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: uuid.UUID, user: dict = Depends(get_current_user)):
    _own_conversation(user, conversation_id)
    db.delete_conversation(user["id"], str(conversation_id))
    shutil.rmtree(conversation_dir(user["id"], str(conversation_id)), ignore_errors=True)
    return {"message": "Conversation deleted."}


@app.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: uuid.UUID, user: dict = Depends(get_current_user)):
    _own_conversation(user, conversation_id)
    return db.list_messages(str(conversation_id))


@app.post("/conversations/{conversation_id}/chat")
def chat(conversation_id: uuid.UUID, req: ChatRequest, user: dict = Depends(get_current_user)):
    conv = _own_conversation(user, conversation_id)
    cid = str(conversation_id)

    history = [{"role": m["role"], "content": m["content"]} for m in db.recent_messages(cid, 10)]
    try:
        result = run_graph(req.message, history, user["id"], cid)
    except Exception as e:
        raise HTTPException(500, f"Agent error: {e}")

    db.add_message(cid, "user", req.message)
    db.add_message(cid, "assistant", result["answer"], result["tools_used"])

    title = req.message.strip()[:60] if conv["title"] == "New chat" else None
    db.touch_conversation(cid, title)
    return {"answer": result["answer"], "tools_used": result["tools_used"], "title": title or conv["title"]}


# ------------------------------------------------------------------ files
@app.post("/conversations/{conversation_id}/upload")
async def upload(conversation_id: uuid.UUID, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Runbooks (pdf/md) are saved for the user; logs and metrics for this conversation."""
    _own_conversation(user, conversation_id)
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB} MB).")
    if not data:
        raise HTTPException(400, "The file is empty.")
    try:
        result = await run_in_threadpool(process_upload, user["id"], str(conversation_id), file.filename, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.touch_conversation(str(conversation_id))
    return {"message": "File uploaded successfully.", **result}


@app.get("/conversations/{conversation_id}/files")
def list_conversation_files(conversation_id: uuid.UUID, user: dict = Depends(get_current_user)):
    _own_conversation(user, conversation_id)
    rows = db.list_files(user["id"], str(conversation_id))
    return {
        "documents": [r for r in rows if r["kind"] == "document"],
        "logs": [r for r in rows if r["kind"] == "log"],
        "metrics": [r for r in rows if r["kind"] == "metrics"],
    }


@app.delete("/files/{file_id}")
def delete_file(file_id: uuid.UUID, user: dict = Depends(get_current_user)):
    row = db.get_file(user["id"], str(file_id))
    if row is None:
        raise HTTPException(404, "File not found")

    if row["kind"] == "document":
        from app.rag.rag import delete_source
        delete_source(user["id"], row["filename"])
    elif row["stored_path"]:
        path = Path(row["stored_path"]).resolve()
        if USERS_DIR.resolve() in path.parents:  # never delete outside our data folder
            path.unlink(missing_ok=True)
    db.delete_file_row(user["id"], str(file_id))
    return {"message": "File deleted."}

