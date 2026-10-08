"""Vector store access + retrieval. Every query is filtered by user_id."""
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from app.config import COLLECTION_NAME, EMBEDDING_MODEL, QDRANT_PATH

qdrant_client = QdrantClient(path=str(QDRANT_PATH))
_embedding_model = None


def get_embedding_model() -> SentenceTransformer:
    """Load the embedding model only when document indexing or search needs it."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def ensure_collection() -> None:
    """Create the collection if it does not exist (fresh clones work)."""
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=get_embedding_model().get_sentence_embedding_dimension(),
                distance=Distance.COSINE,
            ),
        )


def _filter(user_id: str, source: str | None = None) -> Filter:
    must = [FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]
    if source:
        must.append(FieldCondition(key="source", match=MatchValue(value=source)))
    return Filter(must=must)


def search_documents(query: str, user_id: str, top_k: int = 5) -> list[dict]:
    """Top_k most relevant chunks of THIS user's documents, with source + page."""
    if not user_id:
        return []
    ensure_collection()
    flt = _filter(user_id)
    if qdrant_client.count(COLLECTION_NAME, count_filter=flt, exact=True).count == 0:
        return []

    vector = get_embedding_model().encode(query).tolist()
    result = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        query_filter=flt,
        limit=top_k,
        with_payload=True,
    )
    return [
        {
            "text": p.payload["text"],
            "source": p.payload.get("source", "unknown"),
            "page": p.payload.get("page"),
            "score": round(p.score, 3),
        }
        for p in result.points
    ]


def list_sources(user_id: str) -> list[str]:
    """Names of this user's indexed documents."""
    ensure_collection()
    sources, offset = set(), None
    while True:
        points, offset = qdrant_client.scroll(
            COLLECTION_NAME, scroll_filter=_filter(user_id), limit=256, offset=offset,
            with_payload=["source"], with_vectors=False,
        )
        sources.update(p.payload["source"] for p in points)
        if offset is None:
            break
    return sorted(sources)


def delete_source(user_id: str, source: str) -> None:
    ensure_collection()
    qdrant_client.delete(
        COLLECTION_NAME,
        points_selector=FilterSelector(filter=_filter(user_id, source)),
    )
