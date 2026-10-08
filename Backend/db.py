"""PostgreSQL access (users, conversations, messages, files)."""
from contextlib import contextmanager

from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from app.config import DATABASE_URL

_pool = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set in Backend/.env")
        _pool = ThreadedConnectionPool(1, 10, DATABASE_URL)
    return _pool


@contextmanager
def cursor():
    """Yield a dict cursor; commit on success, roll back on error."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def check_schema() -> None:
    """Fail early with a clear error if the tables are missing."""
    with cursor() as cur:
        for table in ("users", "conversations", "messages", "files"):
            cur.execute(f"SELECT 1 FROM {table} LIMIT 1")


# ------------------------------------------------------------------ users
def create_user(username: str, password_hash: str, email: str | None) -> dict:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) "
            "RETURNING id, username",
            (username, email, password_hash),
        )
        return cur.fetchone()


def get_user_by_username(username: str) -> dict | None:
    with cursor() as cur:
        cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
        return cur.fetchone()


def get_user(user_id: str) -> dict | None:
    with cursor() as cur:
        cur.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


# ------------------------------------------------------------------ conversations
def create_conversation(user_id: str, title: str = "New chat") -> dict:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (user_id, title) VALUES (%s, %s) "
            "RETURNING id, title, created_at, updated_at",
            (user_id, title),
        )
        return cur.fetchone()


def list_conversations(user_id: str) -> list[dict]:
    with cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.title, c.updated_at,
                   (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
                   (SELECT count(*) FROM files f WHERE f.conversation_id = c.id) AS file_count
            FROM conversations c
            WHERE c.user_id = %s
            ORDER BY c.updated_at DESC
            """,
            (user_id,),
        )
        return cur.fetchall()


def get_conversation(user_id: str, conversation_id: str) -> dict | None:
    """Returns the conversation only if it belongs to this user."""
    with cursor() as cur:
        cur.execute(
            "SELECT id, title FROM conversations WHERE id = %s AND user_id = %s",
            (conversation_id, user_id),
        )
        return cur.fetchone()


def rename_conversation(user_id: str, conversation_id: str, title: str) -> bool:
    with cursor() as cur:
        cur.execute(
            "UPDATE conversations SET title = %s WHERE id = %s AND user_id = %s",
            (title, conversation_id, user_id),
        )
        return cur.rowcount > 0


def touch_conversation(conversation_id: str, title: str | None = None) -> None:
    with cursor() as cur:
        if title:
            cur.execute(
                "UPDATE conversations SET updated_at = now(), title = %s WHERE id = %s",
                (title, conversation_id),
            )
        else:
            cur.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (conversation_id,))


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    """Messages and file records are removed by ON DELETE CASCADE."""
    with cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE id = %s AND user_id = %s", (conversation_id, user_id))
        return cur.rowcount > 0


# ------------------------------------------------------------------ messages
def add_message(conversation_id: str, role: str, content: str, tools_used: list | None = None) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO messages (conversation_id, role, content, tools_used) VALUES (%s, %s, %s, %s)",
            (conversation_id, role, content, Json(tools_used) if tools_used else None),
        )


def list_messages(conversation_id: str) -> list[dict]:
    with cursor() as cur:
        cur.execute(
            "SELECT id, role, content, tools_used, created_at FROM messages "
            "WHERE conversation_id = %s ORDER BY id",
            (conversation_id,),
        )
        return cur.fetchall()


def recent_messages(conversation_id: str, limit: int = 10) -> list[dict]:
    """The last `limit` messages, oldest first (used as chat history for the agent)."""
    with cursor() as cur:
        cur.execute(
            "SELECT role, content FROM ("
            "  SELECT id, role, content FROM messages WHERE conversation_id = %s ORDER BY id DESC LIMIT %s"
            ") t ORDER BY id",
            (conversation_id, limit),
        )
        return cur.fetchall()


# ------------------------------------------------------------------ files
def save_file(user_id: str, conversation_id: str | None, kind: str, filename: str,
              stored_path: str | None = None, chunks: int | None = None) -> dict:
    """Insert a file record; re-uploading the same name replaces the old record."""
    with cursor() as cur:
        cur.execute(
            "DELETE FROM files WHERE user_id = %s AND kind = %s AND filename = %s "
            "AND conversation_id IS NOT DISTINCT FROM %s::uuid",
            (user_id, kind, filename, conversation_id),
        )
        cur.execute(
            "INSERT INTO files (user_id, conversation_id, kind, filename, stored_path, chunks) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, kind, filename, chunks, created_at",
            (user_id, conversation_id, kind, filename, stored_path, chunks),
        )
        return cur.fetchone()


def list_files(user_id: str, conversation_id: str) -> list[dict]:
    """The user's runbooks (all chats) + the logs/metrics of this conversation."""
    with cursor() as cur:
        cur.execute(
            "SELECT id, kind, filename, chunks, created_at FROM files "
            "WHERE user_id = %s AND (conversation_id = %s OR (kind = 'document' AND conversation_id IS NULL)) "
            "ORDER BY created_at",
            (user_id, conversation_id),
        )
        return cur.fetchall()


def get_file(user_id: str, file_id: str) -> dict | None:
    with cursor() as cur:
        cur.execute(
            "SELECT id, kind, filename, stored_path, conversation_id FROM files WHERE id = %s AND user_id = %s",
            (file_id, user_id),
        )
        return cur.fetchone()


def delete_file_row(user_id: str, file_id: str) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM files WHERE id = %s AND user_id = %s", (file_id, user_id))