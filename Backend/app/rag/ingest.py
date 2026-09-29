from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer


# -------------------------
# 1. Read document
# -------------------------

file_path = Path("app/rag/sample.txt")

text = file_path.read_text(encoding="utf-8")


# -------------------------
# 2. Split into chunks
# -------------------------

splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=50
)

chunks = splitter.split_text(text)


# -------------------------
# 3. Load embedding model
# -------------------------

model = SentenceTransformer("all-MiniLM-L6-v2")


# -------------------------
# 4. Create embeddings
# -------------------------

embeddings = model.encode(chunks)


print(f"Total chunks: {len(chunks)}")
print(f"Embedding dimensions: {len(embeddings[0])}")


for i, chunk in enumerate(chunks):

    print(f"\n--- Chunk {i + 1} ---")

    print(chunk)

    print("\nEmbedding:")
    print(embeddings[i][:5])