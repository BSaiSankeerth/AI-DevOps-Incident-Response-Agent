import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import PointStruct

from app.config import COLLECTION_NAME
from app.rag.rag import delete_source, ensure_collection, get_embedding_model, get_qdrant_client

splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)


def ingest_pages(pages: list[tuple[int, str]], source: str, user_id: str) -> int:
    """
    Chunk each page, embed, and store in Qdrant tagged with the owner's user_id.
    Re-uploading a file with the same name replaces the old version.
    """
    chunks, meta = [], []
    for page_number, text in pages:
        for chunk in splitter.split_text(text):
            chunks.append(chunk)
            meta.append(page_number)

    if not chunks:
        return 0

    ensure_collection()
    delete_source(user_id, source)  # avoid duplicates on re-upload

    embeddings = get_embedding_model().encode(chunks, batch_size=32)
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb.tolist(),
            payload={
                "text": chunk,
                "source": source,
                "page": page,
                "chunk_id": i,
                "user_id": str(user_id),
            },
        )
        for i, (chunk, page, emb) in enumerate(zip(chunks, meta, embeddings))
    ]
    get_qdrant_client().upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points)

