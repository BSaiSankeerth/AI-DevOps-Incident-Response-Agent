"""
Final-answer validation before the agent returns to the user.

Three checks:
  1. Citation validation  – every filename+page cited in the answer must
                            exist in the retrieved_sources metadata returned
                            by rag_tool.  Invalid citations are removed.

  2. Command validation   – kubectl / psql / docker / aws / systemctl
                            patterns are extracted.  A command is allowed only
                            if its exact text appears verbatim in the RAG
                            passages.  Unknown commands are replaced with
                            safe prose.

  3. Calculation validation – percentage/ratio numbers that appear in the
                              answer are checked against the list of values
                              produced by calculator_tool.  Any unverified
                              calculated number triggers a warning appended
                              to the NOT VERIFIED section.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------

# Matches: "inventory-api-runbook.pdf page 3"  or  "runbook.pdf, page 12"
_CITE_RE = re.compile(
    r"(?P<fname>[\w\-]+\.(?:pdf|md|rst|markdown))"
    r"[,\s]+page\s+(?P<page>\d+)",
    re.IGNORECASE,
)


def _build_valid_pages(retrieved_sources: list[dict]) -> dict[str, set[int]]:
    """Map filename -> set of valid page numbers from RAG metadata."""
    valid: dict[str, set[int]] = {}
    for s in retrieved_sources:
        src = (s.get("source") or "").lower().strip()
        page = s.get("page")
        if src:
            valid.setdefault(src, set())
            if isinstance(page, int):
                valid[src].add(page)
    return valid


def _validate_citations(answer: str, retrieved_sources: list[dict]) -> tuple[str, list[str]]:
    violations: list[str] = []
    valid_pages = _build_valid_pages(retrieved_sources)

    def _check(m: re.Match) -> str:
        fname = m.group("fname").lower().strip()
        page  = int(m.group("page"))

        # Accept if filename is known and page is in valid set
        if fname in valid_pages:
            if not valid_pages[fname] or page in valid_pages[fname]:
                return m.group(0)  # valid
            violations.append(
                f"Removed invalid citation: {m.group('fname')} page {page} "
                f"(valid pages: {sorted(valid_pages[fname])})"
            )
            return m.group("fname")  # strip the bogus page reference

        # File was never returned by RAG → remove the whole citation
        violations.append(
            f"Removed citation to unretrieved file: {m.group('fname')} page {page}"
        )
        return "[citation removed]"

    cleaned = _CITE_RE.sub(_check, answer)
    return cleaned, violations


# ---------------------------------------------------------------------------
# Command validation
# ---------------------------------------------------------------------------

# Patterns that indicate an operational command was generated
_CMD_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bkubectl\s+\S+", re.IGNORECASE),
    re.compile(r"\bpsql\s+\S+", re.IGNORECASE),
    re.compile(r"\bdocker\s+(run|exec|restart|stop|rm)\b", re.IGNORECASE),
    re.compile(r"\baws\s+[a-z]+\s+[a-z]", re.IGNORECASE),
    re.compile(r"\bsystemctl\s+(restart|stop|start)\b", re.IGNORECASE),
    re.compile(r"\bsudo\s+\S+", re.IGNORECASE),
    re.compile(r"\bhelm\s+(upgrade|rollback|install)", re.IGNORECASE),
]

_SAFE_REPLACEMENT = "(use the standard operational procedure as described in your runbook)"


def _validate_commands(answer: str, rag_text: str) -> tuple[str, list[str]]:
    violations: list[str] = []
    rag_lower  = (rag_text or "").lower()

    def _check_cmd(m: re.Match) -> str:
        cmd = m.group(0)
        # Command is allowed only if it appears verbatim in the retrieved docs
        if cmd.lower() in rag_lower:
            return cmd
        violations.append(f"Removed unsupported command: {cmd!r}")
        return _SAFE_REPLACEMENT

    cleaned = answer
    for pat in _CMD_PATTERNS:
        cleaned = pat.sub(_check_cmd, cleaned)

    return cleaned, violations


# ---------------------------------------------------------------------------
# Calculation validation
# ---------------------------------------------------------------------------

# Numbers that look like derived calculations (percentages, ratios)
_CALC_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*%|\bratio\s+of\s+\d+(?:\.\d+)?", re.IGNORECASE)


def _validate_calculations(answer: str, calculations: list[str]) -> list[str]:
    """
    Find percentage values in the answer that were NOT produced by
    calculator_tool.  Return warnings (we don't strip numbers, just warn).
    """
    warnings: list[str] = []
    calc_values: set[str] = set()
    for c in calculations:
        # calculator_tool returns strings like "300.0" or "150"
        try:
            calc_values.add(str(float(c)))
            calc_values.add(str(int(float(c))))
        except (ValueError, TypeError):
            calc_values.add(str(c))

    for m in _CALC_RE.finditer(answer):
        raw = m.group(1) or ""
        if not raw:
            continue
        # Allow if within ±0.1 of any calculator result
        try:
            val = float(raw)
        except ValueError:
            continue

        matched = any(
            abs(val - float(cv)) < 0.11
            for cv in calc_values
            if _is_numeric(cv)
        )
        if not matched and val > 1:          # skip trivial values like 0 or 1
            warnings.append(
                f"Unverified calculation: {raw}% not produced by calculator_tool"
            )

    return warnings


def _is_numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_answer(
    answer: str,
    retrieved_sources: list[dict],
    calculations: list[str],
    rag_text: str = "",
) -> tuple[str, list[str]]:
    """
    Run all three validators on the draft answer.

    Returns:
        (cleaned_answer, list_of_violation_messages)

    The cleaned_answer has invalid citations and unsupported commands removed.
    Calculation warnings are appended to the NOT VERIFIED section if present.
    """
    all_violations: list[str] = []

    # 1. Citations
    answer, cite_v = _validate_citations(answer, retrieved_sources)
    all_violations.extend(cite_v)

    # 2. Commands
    answer, cmd_v = _validate_commands(answer, rag_text)
    all_violations.extend(cmd_v)

    # 3. Calculations (warnings only)
    calc_w = _validate_calculations(answer, calculations)
    all_violations.extend(calc_w)

    # Append unverified-calculation warnings to NOT VERIFIED section if present
    if calc_w:
        calc_note = "\n".join(f"- {w}" for w in calc_w)
        if "NOT VERIFIED" in answer:
            answer = re.sub(
                r"(NOT VERIFIED\s*\n)",
                r"\1" + calc_note + "\n",
                answer,
                count=1,
            )
        else:
            answer += "\n\nNOT VERIFIED\n" + calc_note

    return answer, all_violations
