from retrieve import load_translation_memory
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from qdrant_client.http import models
import uuid
from pathlib import Path

def collections_creator(client, collection_name: str):
    # Removing existing collection
    if client.collection_exists(collection_name = collection_name):
        client.delete_collection(collection_name = collection_name)
        print("Collection deleted")
    else:
        print("This collection doesn't exist")
    
    # Creating a collection
    client.create_collection(
        collection_name = collection_name,
        vectors_config = VectorParams(size = 384, distance = Distance.COSINE)
    )
# Splitting points into smaller chunks
def chunk_generator(lst, n):
    """Function to split the list into smaller chunks"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]   
         
def points_inserter(client, tm: list, vectors: list, chunks: int, collection_name: str):
    # Building the points for each record-vector pair
    points = []
    for record, vec in zip(tm, vectors):
        points.append(models.PointStruct(id = str(uuid.UUID(record["id"])), vector=vec.tolist(), payload={"id": record["id"]}))

    points_chunked = chunk_generator(points, chunks)

    # Point insertion
    for chunk in points_chunked:
        client.upsert(
            collection_name = collection_name,
            points = chunk
        )
        print("Chunk added")
    
    # Checking the number of points in the collections
    points_count = client.count(collection_name=collection_name)
    print(f"{points_count.count} added to the collection")


def main():
    """Orchestration: creating collection > inserting points"""
    
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    tm_path = PROJECT_ROOT / "data" / "tm" / "translation_memory.jsonl"

    # Importing the translation memory
    tm = load_translation_memory(tm_path)

    # Loading the model
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Collecting source data
    sources = [r["source"] for r in tm]

    # Vectors
    vectors = model.encode(sources, batch_size=64, normalize_embeddings=True, show_progress_bar=True)
    collection_name = "tm_sources"
    chunk_size = 100
    client = QdrantClient(url="http://localhost:6333")
    collections_creator(client, collection_name)
    points_inserter(client, tm, vectors, chunk_size, collection_name)


if __name__ == "__main__": main()