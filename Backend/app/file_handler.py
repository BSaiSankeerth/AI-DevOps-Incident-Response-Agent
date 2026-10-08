"""
Decides what an uploaded file IS (runbook / log / metrics), stores it for the
right owner, and records it in PostgreSQL.

    .pdf, .md, .markdown, .rst   -> document -> vector DB, owned by the USER (all their chats)
    .log, .out, .jsonl           -> log      -> data/users/<user>/<conversation>/logs
    .csv                         -> metrics  -> data/users/<user>/<conversation>/metrics
    .json                        -> metrics, unless it looks like JSON-lines logs
    .txt                         -> log if most lines look like log lines, else document
"""
import json
import os
import re
import tempfile
from pathlib import Path

from app import db
from app.config import conversation_dir

DOC_EXT = {".pdf", ".md", ".markdown", ".rst"}
LOG_EXT = {".log", ".out", ".jsonl"}
SUPPORTED = sorted(DOC_EXT | LOG_EXT | {".csv", ".json", ".txt"})

_LOG_LINE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\b(INFO|WARN|WARNING|ERROR|DEBUG|CRITICAL|FATAL)\b"
)


def safe_name(filename: str) -> str:
    name = Path(filename or "upload").name
    return re.sub(r"[^A-Za-z0-9._\- ]", "_", name) or "upload"


def _looks_like_log(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()][:200]
    if not lines:
        return False
    hits = sum(1 for l in lines if _LOG_LINE.search(l))
    return hits / len(lines) >= 0.3


def _looks_like_jsonl_logs(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()][:20]
    if len(lines) < 2:
        return False
    ok = 0
    for l in lines:
        try:
            obj = json.loads(l)
            if isinstance(obj, dict) and any(
                k.lower() in ("level", "severity", "message", "msg") for k in obj
            ):
                ok += 1
        except ValueError:
            pass
    return ok / len(lines) >= 0.8


def classify(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in DOC_EXT:
        return "document"
    if ext in LOG_EXT:
        return "log"
    if ext == ".csv":
        return "metrics"
    text = data[:200_000].decode("utf-8", errors="replace")
    if ext == ".json":
        return "log" if _looks_like_jsonl_logs(text) else "metrics"
    if ext == ".txt":
        return "log" if _looks_like_log(text) else "document"
    raise ValueError(f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED)}")


def _store_in_conversation(user_id: str, conversation_id: str, folder: str, filename: str, data: bytes) -> Path:
    target_dir = conversation_dir(user_id, conversation_id) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_bytes(data)
    return path


def process_upload(user_id: str, conversation_id: str, filename: str, data: bytes) -> dict:
    """Store + index an uploaded file. Raises ValueError with a user-friendly message."""
    filename = safe_name(filename)
    kind = classify(filename, data)

    # ---- logs: belong to this conversation
    if kind == "log":
        path = _store_in_conversation(user_id, conversation_id, "logs", filename, data)
        db.save_file(user_id, conversation_id, "log", filename, str(path))
        lines = data.decode("utf-8", errors="replace").count("\n") + 1
        return {"kind": "log", "filename": filename, "detail": f"{lines} lines saved for log analysis"}

    # ---- metrics: belong to this conversation
    if kind == "metrics":
        from app.tools.metrics_tool import parse_metrics_text
        parse_metrics_text(data.decode("utf-8-sig", errors="replace"), filename)  # validates
        if Path(filename).suffix.lower() not in (".json", ".csv"):
            filename += ".json"
        path = _store_in_conversation(user_id, conversation_id, "metrics", filename, data)
        db.save_file(user_id, conversation_id, "metrics", filename, str(path))
        return {"kind": "metrics", "filename": filename, "detail": "metrics saved for analysis"}

    # ---- documents: belong to the USER (searchable from every conversation)
    from app.rag.ingest import ingest_pages
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        from app.rag.pdf_loader import extract_pages_from_pdf
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                f.write(data)
                tmp = f.name
            pages = extract_pages_from_pdf(tmp)
        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        if not pages:
            raise ValueError("No text could be extracted from the PDF (is it a scanned image?).")
    else:
        text = data.decode("utf-8", errors="replace")
        if not text.strip():
            raise ValueError("The file is empty.")
        pages = [(1, text)]

    chunks = ingest_pages(pages, filename, user_id)
    db.save_file(user_id, None, "document", filename, None, chunks)
    return {"kind": "document", "filename": filename, "detail": f"{chunks} chunks indexed",
            "chunks_added": chunks}