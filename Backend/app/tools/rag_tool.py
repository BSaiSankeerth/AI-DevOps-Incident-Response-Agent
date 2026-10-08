from app.config import MAX_TOOL_CHARS
from app.rag.rag import search_documents


def rag_tool(question: str, user_id: str | None = None) -> str:
    """
    Search uploaded runbooks / architecture / deployment docs.
    Every passage starts with ONE header line that carries the file name and
    the page number. Passages have no letters or index numbers, so nothing
    can be mistaken for a page number.
    """
    results = search_documents(question, user_id, top_k=5)
    if not results:
        return ("No documents have been uploaded yet (or nothing matched). "
                "Ask the user to upload a runbook PDF.")

    blocks = []
    for r in results:
        page = f"page {r['page']}" if r["page"] else "page n/a"
        blocks.append(
            f"SOURCE: {r['source']} | {page} | relevance {r['score']}\n"
            f"{r['text']}"
        )
    return "\n=====\n".join(blocks)[:MAX_TOOL_CHARS]