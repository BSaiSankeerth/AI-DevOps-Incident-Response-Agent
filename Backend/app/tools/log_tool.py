from pathlib import Path


LOG_FILE = Path("app/logs/payment-api.log")


def log_tool(query: str) -> str:
    """
    Analyze application logs and return relevant
    errors, warnings, timeouts, and failures.
    """

    if not LOG_FILE.exists():
        return "Log file not found."

    logs = LOG_FILE.read_text(
        encoding="utf-8"
    )

    lines = logs.splitlines()

    # Keywords that indicate potential incidents
    keywords = [
        "ERROR",
        "WARNING",
        "timeout",
        "Timeout",
        "failed",
        "Failed",
        "exhausted",
    ]

    relevant_lines = []

    for line in lines:

        if any(
            keyword in line
            for keyword in keywords
        ):
            relevant_lines.append(line)

    if not relevant_lines:
        return "No relevant errors or warnings found in the logs."

    result = "\n".join(relevant_lines)

    return result


if __name__ == "__main__":

    result = log_tool(
        "Why did the payment service fail?"
    )

    print("\nLog Analysis:")
    print(result)