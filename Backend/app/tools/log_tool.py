from pathlib import Path


LOG_DIR = Path("app/logs")


def log_tool(query: str) -> str:
    """
    Dynamically search application logs for relevant
    errors, warnings, timeouts, failures, and query terms.
    """

    if not LOG_DIR.exists():
        return "Log directory not found."

    log_files = list(LOG_DIR.glob("*.log"))

    if not log_files:
        return "No log files found."

    query_words = query.lower().split()

    results = []

    for log_file in log_files:

        lines = log_file.read_text(
            encoding="utf-8"
        ).splitlines()

        for line in lines:
            line_lower = line.lower()

            # Always include important incident signals
            important = any(
                keyword in line_lower
                for keyword in [
                    "error",
                    "warning",
                    "timeout",
                    "failed",
                    "exhausted",
                    "exception",
                ]
            )

            # Or include lines matching the user's query
            matches_query = any(
                word in line_lower
                for word in query_words
                if len(word) > 2
            )

            if important or matches_query:
                results.append(
                    f"[{log_file.name}] {line}"
                )

    if not results:
        return "No relevant log entries found."

    return "\n".join(results)


if __name__ == "__main__":
    print(
        log_tool(
            "payment service database timeout"
        )
    )