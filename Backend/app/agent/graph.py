"""
LangGraph agent for the AI DevOps Incident Response system.

NEW WORKFLOW (v2):

  START
    │
    ▼
  classify_node          – keyword heuristic: 'incident' or 'simple'
    │
    ▼
  prefetch_node          – for incidents: deterministically call metrics_tool,
    │                      log_tool, rag_tool for any uploaded files
    ▼
  agent_node             – LLM with pre-fetched evidence in system context
    │
    ├──(tool_calls)──▶  tool_node  ──▶  agent_node  (loop until no more calls)
    │
    ▼
  validate_node          – strip invalid citations, invented commands,
    │                      warn about unverified calculations
    ▼
   END

Key guarantees:
  • For incident questions, evidence IS collected even if the LLM "forgets"
    to call tools (requirement 1).
  • AgentState tracks evidence, calculations, retrieved_sources,
    tools_called, validation_status (requirement 8).
  • tool_node prevents duplicate tool calls (requirement 9).
  • validate_node enforces citation / command / calculation correctness
    (requirements 4, 5, 6, 7).
  • SYSTEM_PROMPT enforces OBSERVED/INFERRED/UNKNOWN, root-cause vs
    contributing factor, confidence levels, timeline, and remediation
    structure (requirements 2, 3, 10, 11, 12, 13).
"""
from __future__ import annotations

import json
import os
from typing import TypedDict

from dotenv import load_dotenv
from groq import Groq
from langgraph.graph import END, START, StateGraph

from app.agent.incident_classifier import classify_question
from app.agent.prefetcher import format_prefetch_for_context, prefetch_evidence
from app.agent.validator import validate_answer
from app.config import LLM_MODEL, MAX_TOOL_CHARS, MAX_TOOL_ROUNDS
from app.tools.registry import TOOL_FUNCTIONS, TOOL_SCHEMAS

load_dotenv()


def get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured in environment variables or .env file.")
    return Groq(api_key=api_key)


# ============================================================ SYSTEM PROMPT
SYSTEM_PROMPT = """You are a DevOps Incident Response Agent. You INVESTIGATE problems — you do not just answer questions.

TOOLS AVAILABLE
- metrics_tool : uploaded metrics (CPU, memory, latency, errors, requests, DB connections)
- log_tool     : uploaded application logs
- rag_tool     : uploaded runbooks, architecture docs, deployment guides
- calculator_tool : ALL arithmetic (percent change, error rate, ratios). ALWAYS use this instead of calculating in your head.

INVESTIGATION RULES
1. Evidence already collected by the system is shown under PRE-FETCHED sections above.
   Use that evidence FIRST.  Only call a tool again if:
   (a) the pre-fetched result was empty or "No files found", OR
   (b) you need to drill down with a specific keyword (e.g. log_tool("connection pool")).

2. Use calculator_tool for EVERY derived number:
   - percentage increase / decrease
   - error rate
   - any ratio or comparison
   Never calculate in your head.

3. For simple questions (e.g. "what port does the service use?"), call only the tool(s) needed and answer directly.

CAUSE CLASSIFICATION — use these terms precisely:
- ROOT CAUSE    : The underlying condition that, if fixed, would prevent recurrence.
- TRIGGER       : The event that turned a latent problem into an active incident.
- CONTRIBUTING FACTOR : Something that made the impact worse but was not alone sufficient.
- SYMPTOM       : Observable effect caused by the root cause or trigger.
- UNKNOWN       : Cannot be confirmed from current evidence.

NEVER elevate a contributing factor to a root cause unless the evidence directly proves it.
NEVER invent operational commands (kubectl, psql, docker, aws, systemctl, helm).
Only use commands that appear verbatim in retrieved runbook passages.

EVIDENCE LABELING — every claim must be labeled:
OBSERVED: facts from tool results or user input.
INFERRED: conclusions drawn from combining multiple observed facts.
UNKNOWN:  things that cannot be confirmed from uploaded evidence.

CONFIDENCE LEVELS:
HIGH:   Multiple independent sources support the same conclusion.
MEDIUM: Evidence strongly suggests the cause but one link is unverified.
LOW:    Evidence is incomplete, conflicting, or from a single source.

CITATIONS: Copy filename and page EXACTLY from the SOURCE lines in the pre-fetched runbook section.
Never invent a page number.  Never use the passage letter (A, B, C) as a page number.

TIMELINE: When log/metrics timestamps are available, include a bullet-point timeline.
Never invent timestamps.

INCIDENT ANSWER FORMAT (plain text — no markdown tables, no ** or # symbols):

INCIDENT SUMMARY
<1–2 sentences describing what failed>

KEY NUMBERS
- <metric>: <before> → <after> (<calculated % change using calculator_tool>)

EVIDENCE
OBSERVED:
- <fact> (source: metrics / log file:line / document source name page N)
INFERRED:
- <conclusion drawn from observed facts>
UNKNOWN:
- <what cannot be confirmed>

RELEVANT RUNBOOK
- <filename, page, what it says>   or   "none uploaded"

POSSIBLE CAUSE
<classification: root cause / trigger / contributing factor, with reasoning and confidence level>

INCIDENT TIMELINE (only when timestamps available)
- HH:MM — <event based only on actual timestamps in logs/metrics>

RECOMMENDED NEXT STEPS
IMMEDIATE MITIGATION
1. ...
VERIFY RECOVERY
- Monitor <metric/log pattern> — it should improve within <N minutes>
NEXT INVESTIGATION
- Collect <evidence> to confirm or rule out <hypothesis>
PERMANENT FIX
- <what to change after the incident is fully understood>
DO NOT DO
- <unsafe or runbook-contradicted actions>

NOT VERIFIED
- <anything you could not confirm>

For simple questions, answer briefly without this format."""


# ============================================================ STATE
class AgentState(TypedDict):
    messages: list           # plain dicts (OpenAI/Groq chat format)
    steps: int               # tool rounds consumed
    user_id: str
    conversation_id: str
    incident_type: str       # "incident" | "simple"
    evidence: dict           # {metrics: str|None, logs: str|None, rag: str|None}
    retrieved_sources: list  # [{source: str, page: int|None}, ...]
    calculations: list       # strings produced by calculator_tool
    tools_called: list       # tool names already called (dedup guard)
    failed_tools: list       # tools that raised exceptions
    validation_status: str   # "pending" | "ok" | "fixed"


# ============================================================ HELPERS
def _assistant_to_dict(msg) -> dict:
    """Convert a Groq message object to a plain dict."""
    data = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        data["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
            for tc in msg.tool_calls
        ]
    return data


def _build_system_with_evidence(evidence: dict, failed_tools: list) -> str:
    """
    Prepend pre-fetched evidence to the system prompt so it is visible
    before the LLM produces any tool calls.
    """
    evidence_block = format_prefetch_for_context(
        {**evidence, "failed_tools": failed_tools}
    )
    return evidence_block + "\n\n" + "=" * 60 + "\n\n" + SYSTEM_PROMPT


# ============================================================ NODES

def classify_node(state: AgentState) -> dict:
    """
    Classify the latest user message as 'incident' or 'simple'.
    No LLM call — pure heuristic.
    """
    user_messages = [m for m in state["messages"] if m.get("role") == "user"]
    last_user_text = user_messages[-1]["content"] if user_messages else ""
    incident_type = classify_question(last_user_text)
    return {"incident_type": incident_type}


def prefetch_node(state: AgentState) -> dict:
    """
    For incident questions: deterministically call metrics_tool, log_tool,
    and rag_tool for whatever files exist.  Results go into `evidence`.
    For simple questions: skip (evidence stays as empty dicts/None).
    """
    if state["incident_type"] != "incident":
        return {}

    # Get the user's question for the RAG query
    user_messages = [m for m in state["messages"] if m.get("role") == "user"]
    question = user_messages[-1]["content"] if user_messages else ""

    fetched = prefetch_evidence(question, state["user_id"], state["conversation_id"])

    return {
        "evidence": {
            "metrics": fetched["metrics"],
            "logs":    fetched["logs"],
            "rag":     fetched["rag"],
        },
        "retrieved_sources": fetched["retrieved_sources"],
        "tools_called":      fetched["tools_called"],
        "failed_tools":      fetched["failed_tools"],
    }


def agent_node(state: AgentState) -> dict:
    """
    Call the LLM. For incident investigations, the system message already
    contains all pre-fetched evidence, so the LLM can focus on reasoning.
    """
    out_of_budget = state["steps"] >= MAX_TOOL_ROUNDS

    evidence   = state.get("evidence") or {}
    failed     = state.get("failed_tools") or []

    # Build system prompt (with evidence for incidents, plain for simple)
    if state.get("incident_type") == "incident" and any(evidence.values()):
        system_content = _build_system_with_evidence(evidence, failed)
    else:
        system_content = SYSTEM_PROMPT

    messages = [{"role": "system", "content": system_content}] + state["messages"]

    last_error = None
    for _ in range(2):
        try:
            client = get_groq_client()
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="none" if out_of_budget else "auto",
            )
            reply = _assistant_to_dict(response.choices[0].message)
            return {"messages": state["messages"] + [reply]}
        except Exception as e:
            last_error = e

    reply = {
        "role": "assistant",
        "content": f"Sorry, the language model call failed: {last_error}",
    }
    return {"messages": state["messages"] + [reply]}


def tool_node(state: AgentState) -> dict:
    """
    Execute any tool calls in the last assistant message.
    Tracks `tools_called` to skip redundant calls.
    Records calculator_tool outputs in `calculations`.
    """
    new_messages  = list(state["messages"])
    tools_called  = list(state.get("tools_called") or [])
    calculations  = list(state.get("calculations") or [])
    failed_tools  = list(state.get("failed_tools") or [])
    evidence      = dict(state.get("evidence") or {})

    for call in new_messages[-1].get("tool_calls", []):
        name = call["function"]["name"]
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}

        query_key = args.get("query", args.get("question", args.get("expression", "")))

        # ---- Dedup guard: skip if this exact tool+query already ran --------
        dedup_key = f"{name}:{query_key}"
        if dedup_key in tools_called and name != "calculator_tool":
            print(f"[tool] SKIPPED (duplicate): {name}({args})")
            result = (
                f"[Already called {name} with this query in this investigation. "
                "Use the earlier result above.]"
            )
        else:
            print(f"\n[tool] {name}({args})")
            func = TOOL_FUNCTIONS.get(name)
            if func is None:
                result = f"Unknown tool: {name}"
            else:
                try:
                    result = str(func(
                        args,
                        {"user_id": state["user_id"], "conversation_id": state["conversation_id"]},
                    ))
                    # Track calculator results for validation
                    if name == "calculator_tool":
                        calculations.append(result.strip())
                    if dedup_key not in tools_called:
                        tools_called.append(dedup_key)
                        # Keep short tool name list for tools_used reporting
                        if name not in [t.split(":")[0] for t in tools_called[:-1]]:
                            pass  # already recorded by dedup_key above
                except Exception as e:
                    result = f"Tool {name} failed: {e}"
                    failed_tools.append(f"{name}: {e}")

        print(f"[tool result preview] {result[:300]!r}")

        new_messages.append({
            "role":        "tool",
            "tool_call_id": call["id"],
            "name":        name,
            "content":     result[:MAX_TOOL_CHARS],
        })

    return {
        "messages":     new_messages,
        "steps":        state["steps"] + 1,
        "tools_called": tools_called,
        "calculations": calculations,
        "failed_tools": failed_tools,
    }


def validate_node(state: AgentState) -> dict:
    """
    Final validation before returning the answer to the user.
    - Strip citations not in retrieved_sources
    - Remove invented commands not in RAG text
    - Warn about calculations not from calculator_tool
    """
    last_msg = state["messages"][-1]
    if last_msg.get("role") != "assistant" or not last_msg.get("content"):
        return {"validation_status": "ok"}

    answer           = last_msg["content"]
    retrieved_sources = state.get("retrieved_sources") or []
    calculations      = state.get("calculations") or []
    rag_text          = (state.get("evidence") or {}).get("rag") or ""

    # Also include RAG text from tool messages (LLM may have called rag_tool itself)
    for m in state["messages"]:
        if m.get("role") == "tool" and m.get("name") == "rag_tool":
            rag_text += "\n" + m.get("content", "")

    cleaned, violations = validate_answer(
        answer, retrieved_sources, calculations, rag_text
    )

    if violations:
        print(f"[validate] {len(violations)} violation(s) corrected:")
        for v in violations:
            print(f"  • {v}")

    status = "fixed" if violations else "ok"
    new_messages = list(state["messages"])
    new_messages[-1] = {**last_msg, "content": cleaned}

    return {
        "messages":          new_messages,
        "validation_status": status,
    }


# ============================================================ ROUTING

def route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if last.get("tool_calls"):
        return "tools"
    return "validate"


# ============================================================ GRAPH

builder = StateGraph(AgentState)
builder.add_node("classify", classify_node)
builder.add_node("prefetch", prefetch_node)
builder.add_node("agent",    agent_node)
builder.add_node("tools",    tool_node)
builder.add_node("validate", validate_node)

builder.add_edge(START,      "classify")
builder.add_edge("classify", "prefetch")
builder.add_edge("prefetch", "agent")
builder.add_conditional_edges(
    "agent",
    route_after_agent,
    {"tools": "tools", "validate": "validate"},
)
builder.add_edge("tools",    "agent")
builder.add_edge("validate", END)

graph = builder.compile()


# ============================================================ PUBLIC API

def run_graph(
    question: str,
    history: list[dict] | None,
    user_id: str,
    conversation_id: str,
) -> dict:
    """
    Run the agent for ONE user in ONE conversation.
    Returns {'answer': str, 'tools_used': [str]}.
    """
    messages = list(history or []) + [{"role": "user", "content": question}]

    initial_state: AgentState = {
        "messages":          messages,
        "steps":             0,
        "user_id":           str(user_id),
        "conversation_id":   str(conversation_id),
        "incident_type":     "unknown",
        "evidence":          {"metrics": None, "logs": None, "rag": None},
        "retrieved_sources": [],
        "calculations":      [],
        "tools_called":      [],
        "failed_tools":      [],
        "validation_status": "pending",
    }

    result = graph.invoke(initial_state, config={"recursion_limit": 50})

    # Collect unique tool names (from prefetch + LLM-driven tool calls)
    tools_used: list[str] = []
    seen: set[str] = set()
    for m in result["messages"]:
        if m.get("role") == "tool":
            name = m["name"]
            if name not in seen:
                seen.add(name)
                tools_used.append(name)

    return {
        "answer":     result["messages"][-1]["content"],
        "tools_used": tools_used,
    }
