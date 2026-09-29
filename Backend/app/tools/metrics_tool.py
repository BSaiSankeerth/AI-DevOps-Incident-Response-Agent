import json
from pathlib import Path


METRICS_FILE = Path("app/metrics/payment_metrics.json")


def metrics_tool(query: str) -> str:
    """
    Retrieve application performance metrics
    for the payment service.
    """

    if not METRICS_FILE.exists():
        return "Metrics file not found."

    with open(METRICS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    metrics = data["metrics"]

    return (
        f"Service: {data['service']}\n"
        f"CPU usage: {metrics['cpu_usage_percent']}%\n"
        f"Memory usage: {metrics['memory_usage_percent']}%\n"
        f"Request count: {metrics['request_count']}\n"
        f"Error count: {metrics['error_count']}\n"
        f"Average latency: {metrics['average_latency_ms']} ms\n"
        f"P95 latency: {metrics['p95_latency_ms']} ms"
    )


if __name__ == "__main__":
    result = metrics_tool("payment service metrics")
    print("\nMetrics:")
    print(result)