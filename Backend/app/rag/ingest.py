import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from qdrant_client.models import PointStruct

from app.rag.rag import qdrant_client


COLLECTION_NAME = "devops_documents"

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=50
)


def ingest_document(
    text: str,
    source: str
):
    """
    Split a document into chunks, create embeddings,
    and store the chunks in Qdrant.
    """

    chunks = splitter.split_text(text)

    if not chunks:
        return 0

    embeddings = embedding_model.encode(chunks)

    points = []

    for i, (chunk, embedding) in enumerate(
        zip(chunks, embeddings)
    ):

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding.tolist(),
            payload={
                "text": chunk,
                "source": source,
                "chunk_id": i
            }
        )

        points.append(point)

    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

    return len(chunks)