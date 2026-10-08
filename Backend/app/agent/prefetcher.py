"""
Pre-fetch evidence for incident investigations before the LLM runs.
Checks which file types exist, calls the relevant tools, and returns
structured evidence the agent can include directly in its system context.

This removes the dependency on tool_choice='auto' for incident questions.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.config import conversation_dir
from app.tools.log_tool import log_tool
from app.tools.metrics_tool import metrics_tool
from app.tools.rag_tool import rag_tool

# --- helpers -----------------------------------------------------------------

METRICS_EXT = {".json", ".csv"}
LOG_EXT     = {".log", ".txt", ".out", ".jsonl"}


def _has_files(folder: Path, extensions: set[str]) -> bool:
    if not folder.exists():
        return False
    return any(f.suffix.lower() in extensions for f in folder.iterdir() if f.is_file())


def _parse_rag_sources(rag_text: str) -> list[dict]:
    """
    Extract {source, page} from every SOURCE header the rag_tool returns.
    Format: SOURCE: <filename> | page <N> | relevance <score>
    """
    sources: list[dict] = []
    for m in re.finditer(
        r"SOURCE:\s*(?P<src>\S+)\s*\|\s*page\s*(?P<page>\S+)", rag_text
    ):
        page_raw = m.group("page")
        try:
            page = int(page_raw)
        except ValueError:
            page = None
        sources.append({"source": m.group("src"), "page": page})
    return sources


# --- public API --------------------------------------------------------------

def prefetch_evidence(
    question: str,
    user_id: str,
    conversation_id: str,
) -> dict:
    """
    Checks which file types exist for this conversation and retrieves:
      - metrics evidence (if .csv/.json files exist)
      - log evidence    (if .log/.txt/.out/.jsonl files exist)
      - rag evidence    (if documents are indexed for this user)

    Returns:
    {
        "metrics":          str | None,
        "logs":             str | None,
        "rag":              str | None,
        "retrieved_sources": list[dict],   # [{source, page}, ...]
        "tools_called":     list[str],
        "failed_tools":     list[str],
    }
    """
    conv_dir    = conversation_dir(user_id, conversation_id)
    metrics_dir = conv_dir / "metrics"
    logs_dir    = conv_dir / "logs"

    result: dict = {
        "metrics":           None,
        "logs":              None,
        "rag":               None,
        "retrieved_sources": [],
        "tools_called":      [],
        "failed_tools":      [],
    }

    # ---- metrics ------------------------------------------------------------
    if _has_files(metrics_dir, METRICS_EXT):
        try:
            out = metrics_tool("", metrics_dir)
            # "No metrics files…" means nothing useful
            if out and "No metrics files" not in out:
                result["metrics"] = out
                result["tools_called"].append("metrics_tool")
        except Exception as exc:
            result["failed_tools"].append(f"metrics_tool: {exc}")

    # ---- logs ---------------------------------------------------------------
    if _has_files(logs_dir, LOG_EXT):
        try:
            out = log_tool("", logs_dir)
            if out and "No log files" not in out:
                result["logs"] = out
                result["tools_called"].append("log_tool")
        except Exception as exc:
            result["failed_tools"].append(f"log_tool: {exc}")

    # ---- rag ----------------------------------------------------------------
    # rag_tool is user-scoped (all conversations share the user's documents)
    try:
        out = rag_tool(question, user_id)
        if out and "No documents" not in out:
            result["rag"] = out
            result["retrieved_sources"] = _parse_rag_sources(out)
            result["tools_called"].append("rag_tool")
    except Exception as exc:
        result["failed_tools"].append(f"rag_tool: {exc}")

    return result


def format_prefetch_for_context(evidence: dict) -> str:
    """
    Format pre-fetched evidence as a block that is prepended to the
    agent system prompt so the LLM has all evidence before it reasons.
    """
    parts: list[str] = []

    if evidence["metrics"]:
        parts.append("=== PRE-FETCHED METRICS ===\n" + evidence["metrics"])
    else:
        parts.append("=== PRE-FETCHED METRICS ===\nNo metrics files found for this conversation.")

    if evidence["logs"]:
        parts.append("=== PRE-FETCHED LOGS ===\n" + evidence["logs"])
    else:
        parts.append("=== PRE-FETCHED LOGS ===\nNo log files found for this conversation.")

    if evidence["rag"]:
        parts.append("=== PRE-FETCHED RUNBOOK / DOCUMENTS ===\n" + evidence["rag"])
    else:
        parts.append("=== PRE-FETCHED RUNBOOK / DOCUMENTS ===\nNo documents found for this user.")

    if evidence["failed_tools"]:
        parts.append(
            "=== TOOL FAILURES ===\n"
            + "\n".join(f"- {f}" for f in evidence["failed_tools"])
        )

    return "\n\n".join(parts)
