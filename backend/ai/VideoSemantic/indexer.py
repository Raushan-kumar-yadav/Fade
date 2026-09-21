import chromadb
import hashlib
import math
from pathlib import Path

# ── Embedding strategy ──────────────────────────────────────────────────────────
# Tier 1: fastembed — pure ONNX, zero torch dependency. Works in PyInstaller
#          builds where torch is excluded. Model: BAAI/bge-small-en-v1.5 (384-dim).
# Tier 2: sentence_transformers ONNX backend (dev env with torch installed).
# Tier 3: Pure-Python hash-bag-of-words — zero dependencies, offline, keyword-level.
# IMPORTANT: we ALWAYS provide explicit embeddings to chromadb so it never
# tries to auto-embed (which would trigger a ~23 MB S3 download and crash the
# sandboxed worker process).

_embedder = None
_embedder_type = "hash"

# Tier 1 — fastembed (torch-free, pure ONNX)
try:
    from fastembed import TextEmbedding as _FE
    _fe_model = _FE("BAAI/bge-small-en-v1.5")
    _embedder = _fe_model
    _embedder_type = "fastembed"
    print("[indexer] Using fastembed embedder (Tier 1, torch-free ONNX)", flush=True)
except Exception as _e1:
    # Tier 2 — sentence_transformers ONNX (dev env)
    try:
        from sentence_transformers import SentenceTransformer as _ST
        _embedder = _ST("all-MiniLM-L6-v2", backend="onnx")
        _embedder_type = "sentence_transformers"
        print("[indexer] Using sentence_transformers embedder (Tier 2, ONNX backend)", flush=True)
    except Exception as _e2:
        print(f"[indexer] sentence_transformers unavailable ({_e2}) — using hash-bag-of-words fallback", flush=True)

_EMBED_DIM = 384


def _simple_embed(texts: list[str]) -> list[list[float]]:
    """
    Pure-Python keyword embedding.  Maps each unique word to a bucket in a
    384-dimensional vector via MD5, accumulates TF weights, then L2-normalises.
    No external dependencies, no network, deterministic and consistent.
    """
    result: list[list[float]] = []
    for text in texts:
        vec = [0.0] * _EMBED_DIM
        words = text.lower().split()
        for word in words:
            # Two independent hash functions to reduce collisions
            h1 = int(hashlib.md5(word.encode()).hexdigest(), 16) % _EMBED_DIM
            h2 = int(hashlib.sha1(word.encode()).hexdigest(), 16) % _EMBED_DIM
            vec[h1] += 1.0
            vec[h2] += 0.5
        magnitude = math.sqrt(sum(v * v for v in vec)) or 1.0
        result.append([v / magnitude for v in vec])
    return result


def _encode(texts: list[str]) -> list[list[float]]:
    """Always returns an explicit embeddings list — never None."""
    if _embedder is not None:
        if _embedder_type == "fastembed":
            # fastembed.embed() returns a generator of numpy arrays
            return [v.tolist() for v in _embedder.embed(texts)]
        else:
            # sentence_transformers.encode() returns a single ndarray (batch)
            return _embedder.encode(texts).tolist()
    return _simple_embed(texts)


def _upsert(col, ids: list[str], documents: list[str], metadatas: list[dict]) -> None:
    """Upsert into *col* with explicit embeddings (never triggers chromadb auto-embed)."""
    embs = _encode(documents)
    col.upsert(ids=ids, embeddings=embs, documents=documents, metadatas=metadatas)


def _query(col, query: str, n_results: int) -> dict:
    """Semantic/keyword search using explicit query embedding."""
    q_emb = _encode([query])
    return col.query(query_embeddings=q_emb, n_results=n_results)


# Scratch DB — used when no project is saved yet
_SCRATCH_DB_PATH = str(Path.home() / ".fade" / "chroma_db")
_DEFAULT_DB_PATH = _SCRATCH_DB_PATH

# Active clients
_client: chromadb.PersistentClient = None
_col = None
_img_col = None


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


# Initialise with the default path on import (non-fatal if chromadb fails)
try:
    _ensure_client()
except Exception as _ce:
    print(f"[ChromaDB] Init failed (non-fatal): {_ce}", flush=True)


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


#  Video indexing 

def index_video(asset_id: str, chunks: list[dict]) -> int:
    if not chunks:
        print(f"[ChromaDB] No chunks to index for {asset_id[:8]}", flush=True)
        return 0
    if _col is None:
        print("[ChromaDB] Collection not ready — skipping index_video", flush=True)
        return 0

    total = len(chunks)
    print(f"[ChromaDB] Saving {total} chunks for asset {asset_id[:8]}…", flush=True)

    texts     = [c["text"] for c in chunks]
    ids       = [f"{asset_id}__{i}" for i in range(total)]
    metadatas = [
        {"assetId": asset_id, "start_sec": c["start_sec"], "end_sec": c["end_sec"], "asset_type": "video"}
        for c in chunks
    ]

    for i, (doc, meta) in enumerate(zip(texts, metadatas)):
        preview = doc[:80].replace("\n", " ")
        print(f"[ChromaDB]  [{i+1}/{total}] {meta['start_sec']:.0f}s–{meta['end_sec']:.0f}s → {preview}…", flush=True)

    try:
        _upsert(_col, ids, texts, metadatas)
        print(f"[ChromaDB] ✓ {total} chunks saved for {asset_id[:8]}", flush=True)
        return total
    except Exception as e:
        print(f"[ChromaDB] index_video upsert failed: {e}", flush=True)
        return 0


def get_segments_for_asset(asset_id: str) -> list[dict]:
    """Return all stored transcript segments for *asset_id* sorted by start time."""
    if not _col:
        return []
    try:
        result = _col.get(
            where={"assetId": asset_id},
            include=["documents", "metadatas"],
            limit=2000,
        )
        segments = []
        for doc, meta in zip(result["documents"], result["metadatas"]):
            if not doc or not doc.strip():
                continue
            segments.append({
                "start_s": float(meta.get("start_sec", 0)),
                "end_s":   float(meta.get("end_sec", 0)),
                "text":    doc.strip(),
            })
        segments.sort(key=lambda s: s["start_s"])
        return segments
    except Exception as exc:
        print(f"[ChromaDB] get_segments_for_asset failed: {exc}", flush=True)
        return []


def _try_heal_collection(col_name: str) -> None:
    """
    Heal HNSW corruption by re-upserting all records.
    Non-fatal — any exception is swallowed.
    """
    global _col, _img_col
    try:
        col = _client.get_collection(col_name)
        all_data = col.get(include=["embeddings", "documents", "metadatas"])
        if not all_data["ids"]:
            return
        _client.delete_collection(col_name)
        new_col = _client.get_or_create_collection(
            name=col_name, metadata={"hnsw:space": "cosine"}
        )
        # Update the global reference FIRST so the new (valid) collection is
        # reachable even if the upsert below throws — prevents "does not exist"
        # errors from lingering references to the deleted UUID.
        if col_name == "video_segments":
            _col = new_col
        else:
            _img_col = new_col

        embs = all_data["embeddings"]
        # Rust backend returns numpy arrays — `if embs:` raises ValueError for
        # multi-element arrays. Use explicit None/len check instead.
        has_embs = embs is not None and hasattr(embs, "__len__") and len(embs) > 0
        if has_embs:
            new_col.upsert(ids=all_data["ids"], embeddings=embs,
                           documents=all_data["documents"], metadatas=all_data["metadatas"])
        else:
            new_col.upsert(ids=all_data["ids"],
                           documents=all_data["documents"], metadatas=all_data["metadatas"])
        print(f"[ChromaDB] ✓ Healed HNSW for '{col_name}' ({len(all_data['ids'])} entries)", flush=True)
    except Exception as _e:
        _msg = str(_e).lower()
        if "nothing found on disk" not in _msg and "hnsw" not in _msg:
            print(f"[ChromaDB] Heal note for '{col_name}' (non-fatal): {_e}", flush=True)
        # If heal failed mid-way (collection was deleted but not recreated),
        # ensure _col/_img_col always point to a valid collection.
        try:
            recovery = _client.get_or_create_collection(
                name=col_name, metadata={"hnsw:space": "cosine"}
            )
            if col_name == "video_segments":
                _col = recovery
            else:
                _img_col = recovery
        except Exception:
            pass  # Total failure — already logged above



def _col_count(col) -> int:
    """Safe count that re-inits if the collection UUID became stale."""
    try:
        return col.count()
    except Exception:
        _ensure_client(get_db_path())
        return 0


def search_videos(query: str, top_k: int = 5) -> list[dict]:
    global _col
    if _col is None:
        return []
    try:
        cnt = _col_count(_col)
    except Exception:
        return []

    if cnt == 0:
        return []

    try:
        results = _query(_col, query, min(top_k, cnt))
    except Exception:
        _try_heal_collection("video_segments")
        try:
            cnt2 = _col_count(_col) if _col is not None else 0
            if cnt2 == 0:
                return []
            results = _query(_col, query, min(top_k, cnt2))
        except Exception:
            return []

    hits = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        hits.append({
            "assetId":    meta["assetId"],
            "start_sec":  meta["start_sec"],
            "end_sec":    meta["end_sec"],
            "text":       doc,
            "score":      round(1 - results["distances"][0][i], 4),
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


#  Image indexing 

def index_image(asset_id: str, description: str) -> bool:
    """Store a single image description in the image_assets collection."""
    if not description.strip():
        print(f"[ChromaDB] Empty description for image {asset_id[:8]}, skipping", flush=True)
        return False
    if _img_col is None:
        print("[ChromaDB] Image collection not ready — skipping", flush=True)
        return False

    try:
        _upsert(_img_col, [asset_id], [description],
                [{"assetId": asset_id, "asset_type": "image"}])
        preview = description[:80].replace("\n", " ")
        print(f"[ChromaDB] ✓ Image {asset_id[:8]} saved → {preview}…", flush=True)
        return True
    except Exception as e:
        print(f"[ChromaDB] index_image upsert failed: {e}", flush=True)
        return False


def search_images(query: str, top_k: int = 5) -> list[dict]:
    global _img_col
    if _img_col is None:
        return []
    try:
        cnt = _col_count(_img_col)
    except Exception:
        return []

    if cnt == 0:
        return []

    try:
        results = _query(_img_col, query, min(top_k, cnt))
    except Exception:
        return []

    hits = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        hits.append({
            "assetId":    meta["assetId"],
            "text":       doc,
            "score":      round(1 - results["distances"][0][i], 4),
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
