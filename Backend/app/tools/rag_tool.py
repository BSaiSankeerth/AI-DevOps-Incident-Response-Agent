from app.rag.rag import ask_rag


def rag_tool(question: str) -> str:
    """
    Search the DevOps knowledge base and answer
    the user's question using the retrieved context.
    """

    return ask_rag(question)


if __name__ == "__main__":
    question = "How do I restart the payment service?"

    answer = rag_tool(question)

    print("\nAnswer:")
    print(answer)