from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer("all-MiniLM-L6-v2")

sentences = [
    "The database connection timed out",
    "The database request took too long",
    "The weather is very hot today"
]

embeddings = model.encode(sentences)

similarity_1 = cosine_similarity(
    [embeddings[0]],
    [embeddings[1]]
)

similarity_2 = cosine_similarity(
    [embeddings[0]],
    [embeddings[2]]
)

print("Database vs Database:")
print(similarity_1[0][0])

print("\nDatabase vs Weather:")
print(similarity_2[0][0])