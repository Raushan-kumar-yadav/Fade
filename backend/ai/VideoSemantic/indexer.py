import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path

_DB_PATH   = str(Path(__file__).parent.parent.parent / "chroma_db")
_client    = chromadb.PersistentClient(path=_DB_PATH)
_col       = _client.get_or_create_collection(
    name="video_segments",
    metadata={"hnsw:space": "cosine"},
)
_embedder  = SentenceTransformer("all-MiniLM-L6-v2")   # CPU-only, 80 MB


def index_video(asset_id: str, chunks: list[dict]) -> int:
    if not chunks:
        return 0

    texts      = [c["text"]      for c in chunks]
    embeddings = _embedder.encode(texts).tolist()
    ids        = [f"{asset_id}__{i}" for i in range(len(chunks))]
    metadatas  = [
        {"assetId": asset_id, "start_sec": c["start_sec"], "end_sec": c["end_sec"]}
        for c in chunks
    ]

    _col.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    print(f"[VideoSemantic] indexed {len(chunks)} chunks for {asset_id}")
    return len(chunks)


def search_videos(query: str, top_k: int = 5) -> list[dict]:
    q_emb   = _embedder.encode([query]).tolist()
    results = _col.query(query_embeddings=q_emb, n_results=top_k)

    hits = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        hits.append({
            "assetId":   meta["assetId"],
            "start_sec": meta["start_sec"],
            "end_sec":   meta["end_sec"],
            "text":      doc,
            "score":     round(1 - results["distances"][0][i], 4),  # cosine similarity
        })
    return hits


def delete_video_index(asset_id: str) -> None:
    ids = _col.get(where={"assetId": asset_id})["ids"]
    if ids:
        _col.delete(ids=ids)
        print(f"[VideoSemantic] removed {len(ids)} chunks for {asset_id}")
