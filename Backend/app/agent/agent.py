"""Command-line entry point. The real agent lives in graph.py."""
from app.agent.graph import run_graph


def run_agent(user_question: str) -> str:
    return run_graph(user_question)


if __name__ == "__main__":
    question = input("Describe the incident: ")
    print("\nFinal Answer:\n")
    print(run_agent(question))