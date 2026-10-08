"""
Classify a user question as 'incident', 'simple', or 'unknown'
without making an LLM call.  Used to decide whether to pre-fetch
all evidence tools before the first agent turn.
"""
import re

# Primary: any of these words strongly suggests an investigation is needed
INCIDENT_PRIMARY = {
    "slow", "slower", "slowdown", "latency", "spike", "high",
    "down", "outage", "crash", "crashing", "crashed", "failing",
    "failed", "failure", "degraded", "degradation", "unreachable",
    "timeout", "timeouts", "error", "errors", "exception", "exceptions",
    "5xx", "500", "503", "504", "unavailable",
    "why", "cause", "causing", "caused", "reason", "investigate",
    "diagnose", "diagnosis", "incident", "issue", "problem",
    "connection", "pool", "exhausted", "lock", "deadlock",
    "cpu", "memory", "oom", "oomkilled", "saturation",
    "traffic", "load", "overload", "peak",
    "alert", "pagerduty", "alarm", "triggered",
    "increasing", "increased", "decreased", "dropped", "spike",
    "db", "database", "postgres", "mysql", "query",
}

# Secondary: these alone are too weak but strengthen the signal
INCIDENT_SECONDARY = {
    "after", "since", "deployment", "deploy", "release", "rollout",
    "restart", "rollback", "change", "changed", "update", "upgrade",
    "suddenly", "recently", "started", "begin", "began",
}

_SPLIT = re.compile(r"[^a-z0-9_]+")


def _tokens(text: str) -> set[str]:
    return set(_SPLIT.split(text.lower()))


def classify_question(text: str) -> str:
    """
    Returns one of:
      'incident'  – run the full prefetch (metrics + logs + rag)
      'simple'    – let the LLM decide which tool(s) to call
      'unknown'   – treat as incident (safe default)
    """
    tokens = _tokens(text)
    primary_hits = tokens & INCIDENT_PRIMARY
    secondary_hits = tokens & INCIDENT_SECONDARY

    # Strong signal: ≥1 primary keyword
    if primary_hits:
        return "incident"

    # Weak signal: multiple secondary keywords and a question mark
    if len(secondary_hits) >= 2 and "?" in text:
        return "incident"

    # "what happened" / "what changed" type questions
    lowered = text.lower()
    if re.search(r"\bwhat (happened|changed|went wrong|is wrong|caused)\b", lowered):
        return "incident"

    return "simple"
