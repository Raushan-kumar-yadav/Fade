import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path

# Scratch DB — used when no project is saved yet (keeps data out of the source tree)
_SCRATCH_DB_PATH = str(Path.home() / ".fade" / "chroma_db")
_DEFAULT_DB_PATH = _SCRATCH_DB_PATH  # alias used by legacy callers
_embedder = SentenceTransformer("all-MiniLM-L6-v2")  # CPU-only, 80 MB

# Active clients
_client: chromadb.PersistentClient = None
_col = None      # video_segments
_img_col = None  # image_assets


def _ensure_client(db_path: str | None = None) -> None:
    """Initialise (or re-initialise) the ChromaDB client at *db_path*."""
    global _client, _col, _img_col
    path = db_path or _DEFAULT_DB_PATH
    _client = chromadb.PersistentClient(path=path)
    _col = _client.get_or_create_collection(
        name="video_segments",
        metadata={"hnsw:space": "cosine"},
    )
    _img_col = _client.get_or_create_collection(
        name="image_assets",
        metadata={"hnsw:space": "cosine"},
    )
    print(f"[ChromaDB] Using DB at: {path}", flush=True)


# Initialise with the default path on import
_ensure_client()


def switch_db(db_path: str) -> None:
    """Point the indexer at a different ChromaDB folder (e.g. a loaded project)."""
    _ensure_client(db_path)
    # Proactively heal any HNSW corruption from cross-process writes
    _try_heal_collection("video_segments")
    _try_heal_collection("image_assets")


def get_db_path() -> str:
    return _client.get_settings().persist_directory if _client else _DEFAULT_DB_PATH


def is_asset_indexed(asset_id: str) -> bool:
    """Return True if the asset already has entries in video OR image collection."""
    try:
        if _col and _col.get(where={"assetId": asset_id}, limit=1)["ids"]:
            return True
        if _img_col and _img_col.get(where={"assetId": asset_id}, limit=1)["ids"]:
            return True
    except Exception:
        pass
    return False


#   Video indexing  

def index_video(asset_id: str, chunks: list[dict]) -> int:
    if not chunks:
        print(f"[ChromaDB] No chunks to index for {asset_id[:8]}", flush=True)
        return 0

    total = len(chunks)
    print(f"[ChromaDB] Saving {total} chunks for asset {asset_id[:8]}…", flush=True)

    texts = [c["text"] for c in chunks]
    embeddings = _embedder.encode(texts).tolist()
    ids = [f"{asset_id}__{i}" for i in range(total)]
    metadatas = [
        {"assetId": asset_id, "start_sec": c["start_sec"], "end_sec": c["end_sec"], "asset_type": "video"}
        for c in chunks
    ]

    for i, (doc, meta) in enumerate(zip(texts, metadatas)):
        preview = doc[:80].replace("\n", " ")
        print(f"[ChromaDB]  [{i+1}/{total}] {meta['start_sec']:.0f}s–{meta['end_sec']:.0f}s → {preview}…", flush=True)

    _col.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    print(f"[ChromaDB] ✓ {total} chunks saved for {asset_id[:8]}", flush=True)
    return total


def _try_heal_collection(col_name: str) -> None:
    """
    ChromaDB can get into a state where SQLite has records but HNSW index
    files are missing (e.g. after writing from a different process then
    reopening). Heal it by re-upsertting all records so the HNSW is rebuilt.
    Non-fatal — any exception is swallowed.
    """
    global _col, _img_col
    try:
        col = _client.get_collection(col_name)
        all_data = col.get(include=["embeddings", "documents", "metadatas"])
        if not all_data["ids"]:
            return
        # Delete + recreate forces HNSW rebuild
        _client.delete_collection(col_name)
        new_col = _client.get_or_create_collection(
            name=col_name, metadata={"hnsw:space": "cosine"}
        )
        new_col.upsert(
            ids=all_data["ids"],
            embeddings=all_data["embeddings"],
            documents=all_data["documents"],
            metadatas=all_data["metadatas"],
        )
        if col_name == "video_segments":
            _col = new_col
        else:
            _img_col = new_col
        print(f"[ChromaDB] ✓ Healed HNSW for '{col_name}' ({len(all_data['ids'])} entries)", flush=True)
    except Exception as _e:
        print(f"[ChromaDB] Heal failed for '{col_name}' (non-fatal): {_e}", flush=True)


def search_videos(query: str, top_k: int = 5) -> list[dict]:
    if _col is None or _col.count() == 0:
        return []   # not indexed yet
    q_emb = _embedder.encode([query]).tolist()
    try:
        results = _col.query(query_embeddings=q_emb, n_results=min(top_k, _col.count()))
    except Exception:
        # HNSW index missing/corrupt — try to heal, then retry once
        _try_heal_collection("video_segments")
        try:
            if _col is None or _col.count() == 0:
                return []
            results = _col.query(query_embeddings=q_emb, n_results=min(top_k, _col.count()))
        except Exception:
            return []

    hits = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        hits.append({
            "assetId": meta["assetId"],
            "start_sec": meta["start_sec"],
            "end_sec": meta["end_sec"],
            "text": doc,
            "score": round(1 - results["distances"][0][i], 4),
            "asset_type": meta.get("asset_type", "video"),
        })
    return hits


def delete_video_index(asset_id: str) -> None:
    ids = _col.get(where={"assetId": asset_id})["ids"]
    if ids:
        _col.delete(ids=ids)
        print(f"[ChromaDB] Removed {len(ids)} video chunks for {asset_id[:8]}", flush=True)
    img_ids = _img_col.get(where={"assetId": asset_id})["ids"]
    if img_ids:
        _img_col.delete(ids=img_ids)
        print(f"[ChromaDB] Removed {len(img_ids)} image chunks for {asset_id[:8]}", flush=True)


#   Image indexing  

def index_image(asset_id: str, description: str) -> bool:
    """Store a single image description in the image_assets collection."""
    if not description.strip():
        print(f"[ChromaDB] Empty description for image {asset_id[:8]}, skipping", flush=True)
        return False

    embedding = _embedder.encode([description]).tolist()
    _img_col.upsert(
        ids=[asset_id],
        embeddings=embedding,
        documents=[description],
        metadatas=[{"assetId": asset_id, "asset_type": "image"}],
    )
    preview = description[:80].replace("\n", " ")
    print(f"[ChromaDB] ✓ Image {asset_id[:8]} saved → {preview}…", flush=True)
    return True


def search_images(query: str, top_k: int = 5) -> list[dict]:
    if _img_col is None or _img_col.count() == 0:
        return []   # not indexed yet
    q_emb = _embedder.encode([query]).tolist()
    try:
        results = _img_col.query(query_embeddings=q_emb, n_results=min(top_k, _img_col.count()))
    except Exception:
        return []

    hits = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        hits.append({
            "assetId": meta["assetId"],
            "text": doc,
            "score": round(1 - results["distances"][0][i], 4),
            "asset_type": "image",
        })
    return hits


def search_all(query: str, top_k: int = 5) -> list[dict]:
    """Search both video and image collections, ranked together by score."""
    video_hits = search_videos(query, top_k)
    image_hits = search_images(query, top_k)
    combined = video_hits + image_hits
    combined.sort(key=lambda h: h["score"], reverse=True)
    return combined[:top_k]
