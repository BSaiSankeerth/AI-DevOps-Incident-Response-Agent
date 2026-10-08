"""
Log analyzer. Works on ANY uploaded log file (plain text, ISO/nginx timestamps,
or JSON-lines). Instead of dumping raw lines it returns an investigation
summary: level counts, time range, first error, error categories, repeated
messages, HTTP status/latency stats, and the most relevant lines.
"""
import json
import re
import statistics
from collections import Counter
from pathlib import Path

from app.config import MAX_TOOL_CHARS

LOG_EXTENSIONS = {".log", ".txt", ".out", ".jsonl"}

TS_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
    r"|\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2})"
)
LEVEL_RE = re.compile(
    r"\b(TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|CRITICAL|FATAL|SEVERE)\b",
    re.IGNORECASE,
)
HTTP_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD)\s+(\S+)\s+(\d{3})\b")
LATENCY_RE = re.compile(r"(\d+(?:\.\d+)?)\s?ms\b", re.IGNORECASE)

LEVEL_ALIASES = {
    "WARN": "WARNING", "ERR": "ERROR", "SEVERE": "ERROR",
    "FATAL": "CRITICAL",
}
BAD_LEVELS = {"WARNING", "ERROR", "CRITICAL"}

# category -> regex that identifies it
CATEGORIES = {
    "timeout": r"time[d ]?-?out",
    "connection refused/failed": r"connection (refused|reset|failed|closed)|failed to connect|unable to connect",
    "connection pool exhausted": r"pool.{0,20}(exhaust|full|limit)|too many (connections|clients)|max(imum)? connections",
    "database": r"postgres|mysql|database|sql|deadlock|query took",
    "out of memory": r"out of memory|\boom\b|oomkilled|memory (limit|pressure)|java heap",
    "disk": r"no space left|disk (full|usage)",
    "http 5xx": r"\b5\d\d\b",
    "authentication": r"unauthori[sz]ed|forbidden|auth(entication)? failed|invalid token|\b40[13]\b",
    "dns/network": r"\bdns\b|name resolution|unreachable|network",
    "tls/certificate": r"certificate|ssl|tls|handshake",
    "rate limiting": r"rate.?limit|throttl|\b429\b",
    "kubernetes": r"crashloop|imagepull|evicted|readiness|liveness|oomkilled|back-?off",
    "exception": r"exception|traceback|stack ?trace|panic",
    "deployment/restart": r"deploy|restart|started|starting|shutdown|rollout|version",
}
CATEGORY_RES = {k: re.compile(v, re.IGNORECASE) for k, v in CATEGORIES.items()}

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "why", "how",
    "are", "was", "were", "has", "have", "had", "our", "your", "api", "app",
    "service", "services", "application", "log", "logs", "check", "analyze",
    "analyse", "investigate", "find", "show", "look", "search", "issue",
    "issues", "incident", "problem", "errors", "error", "any", "all", "get",
    "after", "before", "about", "into", "latest", "recent", "please", "high",
    "increase", "increased", "slow", "uploaded", "file", "files",
}


def _parse_line(raw: str) -> dict:
    """Turn one raw line into a structured record."""
    line = raw.rstrip()
    entry = {"raw": line, "ts": None, "level": None, "msg": line}

    stripped = line.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                low = {str(k).lower(): v for k, v in obj.items()}
                entry["ts"] = str(
                    low.get("timestamp") or low.get("time") or low.get("ts")
                    or low.get("@timestamp") or ""
                ) or None
                lvl = str(low.get("level") or low.get("severity") or "").upper()
                entry["level"] = LEVEL_ALIASES.get(lvl, lvl) or None
                entry["msg"] = str(low.get("message") or low.get("msg") or line)
                # compact, readable form instead of the raw JSON blob
                entry["raw"] = " ".join(x for x in (entry["ts"], entry["level"], entry["msg"]) if x)
                return entry
        except (ValueError, TypeError):
            pass

    ts = TS_RE.search(line)
    if ts:
        entry["ts"] = ts.group(1)
    lvl = LEVEL_RE.search(line)
    if lvl:
        name = lvl.group(1).upper()
        entry["level"] = LEVEL_ALIASES.get(name, name)
    return entry


def _normalize(msg: str) -> str:
    """Strip timestamps/numbers so repeated errors group together."""
    msg = TS_RE.sub("", msg)
    msg = LEVEL_RE.sub("", msg)
    msg = re.sub(r"\b\d+(\.\d+)?(ms|s|%)?\b", "#", msg)
    return re.sub(r"\s+", " ", msg).strip(" -:[]")[:140]


def _is_error_line(e: dict) -> bool:
    if e["level"] in BAD_LEVELS:
        return True
    if e["level"] is None:
        low = e["raw"].lower()
        return any(w in low for w in ("error", "exception", "failed", "timeout", "refused", "fatal"))
    return False


def _percentile(values: list[float], pct: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round((pct / 100) * (len(s) - 1))))]


def _query_terms(query: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_\-\.]{3,}", query.lower())
    return [w for w in words if w not in STOPWORDS]


def _load_entries(log_dir) -> tuple[list[dict], list[str]]:
    log_dir = Path(log_dir) if log_dir else None
    files = sorted(
        p for p in log_dir.glob("*") if p.is_file() and p.suffix.lower() in LOG_EXTENSIONS
    ) if log_dir and log_dir.exists() else []
    entries, names = [], []
    for path in files:
        names.append(path.name)
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            e = _parse_line(raw)
            e["file"], e["line_no"] = path.name, n
            entries.append(e)
    return entries, names


def log_tool(query: str = "", log_dir=None) -> str:
    """Analyze uploaded logs; `query` focuses the search (keywords, error names...)."""
    entries, names = _load_entries(log_dir)
    if not names:
        return "No log files have been uploaded to this conversation yet. Ask the user to attach a .log file."
    if not entries:
        return f"Log files found ({', '.join(names)}) but they are empty."

    out = []

    # ---- 1. Overview
    out.append(f"LOG FILES: {', '.join(names)}  ({len(entries)} lines)")
    levels = Counter(e["level"] for e in entries if e["level"])
    if levels:
        out.append("LEVEL COUNTS: " + ", ".join(f"{k}={v}" for k, v in levels.most_common()))
    stamps = [e["ts"] for e in entries if e["ts"]]
    if stamps:
        out.append(f"TIME RANGE: {stamps[0]}  ->  {stamps[-1]}")

    # ---- 2. Errors
    errors = [e for e in entries if _is_error_line(e)]
    out.append(f"ERROR/WARNING LINES: {len(errors)}")
    first_error_idx = None
    if errors:
        first = errors[0]
        first_error_idx = entries.index(first)
        out.append(f"FIRST PROBLEM: [{first['file']}:{first['line_no']}] {first['raw'][:200]}")
        last = errors[-1]
        out.append(f"LAST PROBLEM:  [{last['file']}:{last['line_no']}] {last['raw'][:200]}")

    # ---- 3. Categories
    cat_counts = {}
    for name, rx in CATEGORY_RES.items():
        if name in ("deployment/restart", "http 5xx"):
            continue  # handled separately
        n = sum(1 for e in errors if rx.search(e["raw"]))
        if n:
            cat_counts[name] = n
    if cat_counts:
        out.append("ERROR CATEGORIES: " + ", ".join(
            f"{k}={v}" for k, v in sorted(cat_counts.items(), key=lambda kv: -kv[1])))

    # ---- 4. Repeated messages
    grouped = Counter(_normalize(e["msg"]) for e in errors)
    if grouped:
        out.append("MOST REPEATED PROBLEMS:")
        for msg, n in grouped.most_common(6):
            out.append(f"  {n}x  {msg}")

    # ---- 5. HTTP + latency
    statuses, latencies, lat_before, lat_after = Counter(), [], [], []
    for i, e in enumerate(entries):
        m = HTTP_RE.search(e["raw"])
        if not m:
            continue
        statuses[m.group(3)] += 1
        lm = LATENCY_RE.search(e["raw"][m.end():])
        if lm:
            v = float(lm.group(1))
            latencies.append(v)
            if first_error_idx is not None:
                (lat_before if i < first_error_idx else lat_after).append(v)
    if statuses:
        total = sum(statuses.values())
        n5 = sum(v for k, v in statuses.items() if k.startswith("5"))
        n4 = sum(v for k, v in statuses.items() if k.startswith("4"))
        out.append(
            f"HTTP REQUESTS IN LOGS: {total} total, 5xx={n5}, 4xx={n4}, "
            f"status breakdown: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items()))
        )
    if latencies:
        out.append(
            f"REQUEST LATENCY IN LOGS (ms): avg={statistics.mean(latencies):.0f}, "
            f"p95={_percentile(latencies, 95):.0f}, max={max(latencies):.0f}, n={len(latencies)}"
        )
        if lat_before and lat_after:
            out.append(
                f"LATENCY BEFORE FIRST PROBLEM: avg={statistics.mean(lat_before):.0f} ms (n={len(lat_before)}); "
                f"AFTER: avg={statistics.mean(lat_after):.0f} ms (n={len(lat_after)})"
            )

    # ---- 6. Deployment / restart markers
    markers = [e for e in entries if re.search(
        r"(?i:deploy|rollout|restart|version|released|migrat|started|config|pool_size)|[A-Z][A-Z_]{3,}=", e["raw"])]
    if markers:
        out.append("DEPLOY / STARTUP / CONFIG MARKERS (compare settings before vs after):")
        for e in markers[:8]:
            out.append(f"  [{e['file']}:{e['line_no']}] {e['raw'][:160]}")

    # ---- 7. Lines relevant to the query
    terms = _query_terms(query)
    # ignore words that appear on most lines (e.g. the service name) - they filter nothing
    if len(terms) > 1:
        terms = [t for t in terms
                 if sum(t in e["raw"].lower() for e in entries) <= 0.5 * len(entries)] or terms
    if terms:
        hits = [e for e in entries if any(t in e["raw"].lower() for t in terms)]
        out.append(f"LINES MATCHING {terms}: {len(hits)}")
        for e in hits[:15]:
            out.append(f"  [{e['file']}:{e['line_no']}] {e['raw'][:200]}")
        if len(hits) > 15:
            out.append(f"  ... {len(hits) - 15} more matching lines not shown")
    else:
        out.append("KEY ERROR/WARNING LINES (first 15):")
        for e in errors[:15]:
            out.append(f"  [{e['file']}:{e['line_no']}] {e['raw'][:200]}")
        if len(errors) > 15:
            out.append(f"  ... {len(errors) - 15} more not shown (call log_tool again with a keyword to drill in)")

    result = "\n".join(out)
    if len(result) > MAX_TOOL_CHARS:
        result = result[:MAX_TOOL_CHARS] + "\n...[truncated; call log_tool with a narrower keyword]"
    return result


if __name__ == "__main__":
    import sys
    print(log_tool(sys.argv[2] if len(sys.argv) > 2 else "", sys.argv[1]))  # python -m app.tools.log_tool <folder> [query]