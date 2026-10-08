"""
Metrics analyzer. Accepts ANY uploaded .json or .csv metrics file:
  * snapshot JSON  {"cpu": 72, "memory": {"percent": 81}}
  * list-of-records / time-series JSON
  * CSV time series (timestamp,cpu,memory,latency_ms,...)
It flattens the data, finds the metrics relevant to the query, and for time
series reports first/last/min/max/avg/peak and the change over time.
"""
import csv
import io
import json
import re
from pathlib import Path

from app.config import MAX_TOOL_CHARS

METRIC_EXTENSIONS = {".json", ".csv"}
TIME_KEYS = ("timestamp", "time", "ts", "date", "datetime", "@timestamp")

# words in a user query -> substrings to look for in metric names
SYNONYMS = {
    "cpu": ["cpu", "processor"],
    "memory": ["mem", "ram", "heap"],
    "ram": ["mem", "ram"],
    "latency": ["latency", "response_time", "duration", "p50", "p90", "p95", "p99", "rt_"],
    "slow": ["latency", "response_time", "duration", "p95", "p99"],
    "response": ["latency", "response", "duration"],
    "error": ["error", "fail", "5xx", "exception"],
    "failure": ["error", "fail", "5xx"],
    "request": ["request", "rps", "qps", "throughput", "traffic", "count"],
    "traffic": ["request", "rps", "qps", "traffic", "throughput"],
    "throughput": ["throughput", "rps", "qps", "request"],
    "database": ["db", "database", "postgres", "mysql", "query", "connection", "pool"],
    "db": ["db", "database", "query", "connection", "pool"],
    "connection": ["connection", "conn", "pool"],
    "pool": ["pool", "connection"],
    "disk": ["disk", "io", "storage"],
    "network": ["network", "net_", "bandwidth", "packet"],
    "pod": ["pod", "restart", "container"],
    "restart": ["restart"],
    "queue": ["queue", "backlog", "lag"],
    "thread": ["thread"],
    "gc": ["gc", "garbage"],
}


# ------------------------------------------------------------------ loading
def _to_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().rstrip("%").replace(",", "")
        cleaned = re.sub(r"\s?(ms|s|mb|gb|kb)$", "", cleaned, flags=re.I)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _flatten(obj, prefix="") -> dict:
    flat = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        pass  # lists of records are handled separately
    else:
        flat[prefix.rstrip(".")] = obj
    return flat


def _find_records(obj):
    """Return the biggest list of dicts found anywhere in the JSON, else None."""
    best = None
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        best = obj
    elif isinstance(obj, dict):
        for v in obj.values():
            found = _find_records(v)
            if found and (best is None or len(found) > len(best)):
                best = found
    return best


def parse_metrics_text(text: str, filename: str):
    """Return ('snapshot', {name: value}) or ('series', [row dicts]). Raises ValueError."""
    if filename.lower().endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            raise ValueError("CSV has no data rows")
        return "series", [{(k or "").strip(): v for k, v in r.items()} for r in rows]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    records = _find_records(data)
    if records and len(records) > 1:
        return "series", [_flatten(r) for r in records]
    return "snapshot", _flatten(data)


# ------------------------------------------------------------------ helpers
def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}"


def _expand_query(query: str) -> list[str]:
    q = query.lower()
    terms = set(re.findall(r"[a-z0-9_]{3,}", q))
    for word, subs in SYNONYMS.items():
        if word in q:
            terms.update(subs)
    return sorted(terms)


def _matches(name: str, terms: list[str]) -> bool:
    n = name.lower()
    return any(t in n for t in terms)


def _find_key(flat: dict, include: list[str], exclude: list[str] = ()) -> str | None:
    for k in flat:
        kl = k.lower()
        if any(i in kl for i in include) and not any(x in kl for x in exclude):
            if _to_number(flat[k]) is not None:
                return k
    return None


# ------------------------------------------------------------------ snapshot
def _describe_snapshot(name: str, flat: dict, terms: list[str]) -> list[str]:
    numeric = {k: _to_number(v) for k, v in flat.items() if _to_number(v) is not None}
    text_meta = {k: v for k, v in flat.items()
                 if _to_number(v) is None and isinstance(v, (str, int, float))}
    matched = {k: v for k, v in numeric.items() if _matches(k, terms)} if terms else {}
    selected = {**matched, **{k: v for k, v in numeric.items() if k not in matched}}
    selected = dict(list(selected.items())[:40])

    lines = [f"FILE {name} (snapshot)"]
    for k, v in list(text_meta.items())[:4]:
        lines.append(f"  {k}: {v}")
    for k, v in selected.items():
        lines.append(f"  {k}: {_fmt(v)}")

    err = _find_key(flat, ["error", "fail", "5xx"], ["rate", "percent"])
    req = _find_key(flat, ["request", "total", "count"], ["error", "fail"])
    if err and req and err != req and numeric[req] > 0:
        lines.append(
            f"  DERIVED error rate: {numeric[err] / numeric[req] * 100:.2f}% "
            f"({_fmt(numeric[err])} / {_fmt(numeric[req])})"
        )
    lines.append("  NOTE: single snapshot, no baseline/history -> cannot show trends.")
    return lines


# ------------------------------------------------------------------ series
def _describe_series(name: str, rows: list[dict], terms: list[str]) -> list[str]:
    time_col = next((c for c in rows[0] if c.lower() in TIME_KEYS), None)
    columns = [c for c in rows[0] if c != time_col]
    series = {}
    for c in columns:
        vals = [_to_number(r.get(c)) for r in rows]
        if sum(v is not None for v in vals) >= max(2, len(vals) // 2):
            series[c] = vals

    matched = [c for c in series if _matches(c, terms)] if terms else []
    # matching metrics first, but NEVER hide the others (agent needs CPU/memory/DB for correlation)
    chosen = (matched + [c for c in series if c not in matched])[:20]

    lines = [f"FILE {name} (time series, {len(rows)} rows"
             + (f", {rows[0][time_col]} -> {rows[-1][time_col]}" if time_col else "") + ")"]
    for c in chosen:
        pairs = [(i, v) for i, v in enumerate(series[c]) if v is not None]
        vals = [v for _, v in pairs]
        first, last = vals[0], vals[-1]
        peak_i = max(pairs, key=lambda p: p[1])[0]
        change = f"{(last - first) / first * 100:+.1f}%" if first else "n/a"
        peak_at = f" at {rows[peak_i][time_col]}" if time_col else ""
        line = (f"  {c}: first={_fmt(first)} last={_fmt(last)} min={_fmt(min(vals))} "
                f"max={_fmt(max(vals))}{peak_at} avg={_fmt(sum(vals) / len(vals))} change={change}")
        if len(vals) >= 6:
            half = len(vals) // 2
            a, b = sum(vals[:half]) / half, sum(vals[half:]) / (len(vals) - half)
            if a:
                line += f" | 1st-half avg={_fmt(a)} vs 2nd-half avg={_fmt(b)} ({(b - a) / a * 100:+.1f}%)"
        lines.append(line)
    if len(series) > len(chosen):
        lines.append(f"  ... {len(series) - len(chosen)} other metrics not shown (ask about them by name)")
    return lines


# ------------------------------------------------------------------ tool
def metrics_tool(query: str = "", metrics_dir=None) -> str:
    metrics_dir = Path(metrics_dir) if metrics_dir else None
    files = sorted(
        p for p in metrics_dir.glob("*") if p.is_file() and p.suffix.lower() in METRIC_EXTENSIONS
    ) if metrics_dir and metrics_dir.exists() else []
    if not files:
        return "No metrics files have been uploaded to this conversation yet. Ask the user to attach a .json or .csv metrics file."

    terms = _expand_query(query)
    out = []
    for path in files:
        try:
            kind, data = parse_metrics_text(path.read_text(encoding="utf-8-sig", errors="replace"), path.name)
            out += _describe_snapshot(path.name, data, terms) if kind == "snapshot" \
                else _describe_series(path.name, data, terms)
        except Exception as e:  # never crash the agent
            out.append(f"FILE {path.name}: could not be parsed ({e})")
        out.append("")

    result = "\n".join(out).strip()
    if len(result) > MAX_TOOL_CHARS:
        result = result[:MAX_TOOL_CHARS] + "\n...[truncated]"
    return result


if __name__ == "__main__":
    import sys
    print(metrics_tool(sys.argv[2] if len(sys.argv) > 2 else "", sys.argv[1]))  # python -m app.tools.metrics_tool <folder> [query]