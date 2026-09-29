from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


COLLECTION_NAME = "devops_documents"


# Connect to Qdrant
client = QdrantClient(path="qdrant_storage")


# Load embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")


# User's question
question = "How do I restart the payment service?"


# Convert question into vector
query_vector = model.encode(question).tolist()


# Search Qdrant
results = client.query_points(
    collection_name=COLLECTION_NAME,
    query=query_vector,
    limit=2
)


print("\nSearch results:\n")


for result in results.points:

    print("Score:", result.score)
    print("Source:", result.payload["source"])
    print("Chunk:", result.payload["chunk_id"])
    print("Text:")
    print(result.payload["text"])

    print("-" * 60)


client.close()