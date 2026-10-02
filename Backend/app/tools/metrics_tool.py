import json
from pathlib import Path


METRICS_FILE = Path("app/metrics/payment_metrics.json")


def metrics_tool(query: str) -> str:
    """
    Retrieve relevant application performance metrics
    based on the user's query.
    """

    if not METRICS_FILE.exists():
        return "Metrics file not found."

    with open(METRICS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    metrics = data["metrics"]
    query = query.lower()

    results = []

    # CPU
    if "cpu" in query:
        results.append(
            f"CPU usage: {metrics['cpu_usage_percent']}%"
        )

    # Memory
    if "memory" in query or "ram" in query:
        results.append(
            f"Memory usage: {metrics['memory_usage_percent']}%"
        )

    # Requests
    if "request" in query or "traffic" in query:
        results.append(
            f"Request count: {metrics['request_count']}"
        )

    # Errors
    if "error" in query:
        results.append(
            f"Error count: {metrics['error_count']}"
        )

    # Average latency
    if "latency" in query:
        results.append(
            f"Average latency: {metrics['average_latency_ms']} ms"
        )
        results.append(
            f"P95 latency: {metrics['p95_latency_ms']} ms"
        )

    # If the query is broad, return all metrics
    if not results:
        results = [
            f"Service: {data['service']}",
            f"CPU usage: {metrics['cpu_usage_percent']}%",
            f"Memory usage: {metrics['memory_usage_percent']}%",
            f"Request count: {metrics['request_count']}",
            f"Error count: {metrics['error_count']}",
            f"Average latency: {metrics['average_latency_ms']} ms",
            f"P95 latency: {metrics['p95_latency_ms']} ms",
        ]
    else:
        results.insert(
            0,
            f"Service: {data['service']}"
        )

    return "\n".join(results)


if __name__ == "__main__":
    result = metrics_tool("payment service latency")
    print("\nMetrics:")
    print(result)