import os

from dotenv import load_dotenv
from groq import Groq
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


# -------------------------
# Configuration
# -------------------------

load_dotenv()

COLLECTION_NAME = "devops_documents"


# -------------------------
# Clients
# -------------------------

groq_client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

qdrant_client = QdrantClient(
    path="qdrant_storage"
)

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)


# -------------------------
# RAG function
# -------------------------

def ask_rag(question: str) -> str:

    # 1. Convert question into embedding
    query_vector = embedding_model.encode(
        question
    ).tolist()


    # 2. Search Qdrant
    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=2
    )


    # 3. Extract retrieved text
    context = "\n\n".join(
        result.payload["text"]
        for result in results.points
    )


    # 4. Send context + question to Groq
    prompt = f"""
You are a DevOps assistant.

Answer the user's question using ONLY the
provided context.

If the answer is not present in the context,
say that you don't have enough information.

Context:
{context}

Question:
{question}
"""


    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )


    return response.choices[0].message.content


# -------------------------
# Test
# -------------------------

if __name__ == "__main__":

    question = "What port does the payment service run on?"

    answer = ask_rag(question)

    print("\nAnswer:")
    print(answer)

    qdrant_client.close()