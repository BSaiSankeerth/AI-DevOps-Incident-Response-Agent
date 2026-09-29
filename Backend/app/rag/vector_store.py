from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer


# -------------------------
# 1. Configuration
# -------------------------

COLLECTION_NAME = "devops_documents"

# Connect to local Qdrant
client = QdrantClient(path="qdrant_storage")


# -------------------------
# 2. Read document
# -------------------------

file_path = Path("app/rag/sample.txt")

text = file_path.read_text(encoding="utf-8")


# -------------------------
# 3. Split document
# -------------------------

splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=50
)

chunks = splitter.split_text(text)

print(f"Total chunks: {len(chunks)}")


# -------------------------
# 4. Create embeddings
# -------------------------

model = SentenceTransformer("all-MiniLM-L6-v2")

embeddings = model.encode(chunks)


# -------------------------
# 5. Create Qdrant collection
# -------------------------

if not client.collection_exists(COLLECTION_NAME):

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE
        )
    )

    print("Collection created.")

else:

    print("Collection already exists.")


# -------------------------
# 6. Create Qdrant points
# -------------------------

points = []

for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):

    point = PointStruct(
        id=i,
        vector=embedding.tolist(),
        payload={
            "text": chunk,
            "source": "sample.txt",
            "chunk_id": i
        }
    )

    points.append(point)


# -------------------------
# 7. Insert into Qdrant
# -------------------------

client.upsert(
    collection_name=COLLECTION_NAME,
    points=points
)

print("Chunks successfully stored in Qdrant!")


# -------------------------
# 8. Close connection
# -------------------------

client.close()