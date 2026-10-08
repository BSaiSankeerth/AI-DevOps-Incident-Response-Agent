"""One place that defines every tool: its schema (for the LLM) and its function."""
from app.config import conversation_dir
from app.tools.calculator_tool import calculator_tool
from app.tools.log_tool import log_tool
from app.tools.metrics_tool import metrics_tool
from app.tools.rag_tool import rag_tool


def _schema(name: str, description: str, param: str, param_desc: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {param: {"type": "string", "description": param_desc}},
                "required": [param],
            },
        },
    }


TOOL_SCHEMAS = [
    _schema(
        "rag_tool",
        "Search the uploaded runbooks, architecture docs, deployment guides and "
        "troubleshooting documents. Returns matching passages with file name and page.",
        "question", "What to look up, e.g. 'high latency after deployment troubleshooting steps'.",
    ),
    _schema(
        "log_tool",
        "Analyze the uploaded application logs. Returns level counts, time range, first "
        "error, error categories, repeated errors, HTTP 5xx and latency in the logs, and "
        "matching lines. Call again with a specific keyword to drill down.",
        "query", "Keywords or error text to focus on (e.g. 'timeout', 'connection pool'). May be empty.",
    ),
    _schema(
        "metrics_tool",
        "Read the uploaded metrics (CPU, memory, latency, error count, request count, DB "
        "connections, ...). For time series it returns first/last/min/max/avg/peak and change.",
        "query", "Which metrics to look at (e.g. 'latency and cpu'). May be empty for all metrics.",
    ),
    _schema(
        "calculator_tool",
        "Accurate arithmetic: percentage increase, error rate, ratios, differences. "
        "ALWAYS use this instead of calculating in your head.",
        "expression", "Math expression, e.g. '((800 - 200) / 200) * 100'.",
    ),
]

def _folder(ctx: dict, name: str):
    """logs/ or metrics/ folder of the CURRENT conversation. ids come from the server, never from the LLM."""
    return conversation_dir(ctx["user_id"], ctx["conversation_id"]) / name


# every function receives (arguments_from_llm, ctx) where ctx = {"user_id", "conversation_id"}
TOOL_FUNCTIONS = {
    "rag_tool": lambda a, ctx: rag_tool(a.get("question", ""), ctx["user_id"]),
    "log_tool": lambda a, ctx: log_tool(a.get("query", ""), _folder(ctx, "logs")),
    "metrics_tool": lambda a, ctx: metrics_tool(a.get("query", ""), _folder(ctx, "metrics")),
    "calculator_tool": lambda a, ctx: calculator_tool(a.get("expression", "")),
}
