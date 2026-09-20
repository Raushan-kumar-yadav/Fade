from fastapi import APIRouter, Query, HTTPException

try:
    from ..ai.VideoSemantic.indexer import search_videos, delete_video_index
    _SEARCH_AVAILABLE = True
except Exception as _e:
    print(f"[search] Semantic search disabled: {_e}", flush=True)
    _SEARCH_AVAILABLE = False
    def search_videos(q, top_k=5): return []       # type: ignore[misc]
    def delete_video_index(asset_id): pass          # type: ignore[misc]

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/video")
def search_video(
    q: str = Query(..., description="Natural language query, e.g. 'car crash scene'"),
    top_k: int = Query(5, ge=1, le=20),
):
    """
    Search imported videos by visual content or speech.
    Returns ranked segments with assetId and timestamp range.
    """
    if not _SEARCH_AVAILABLE:
        raise HTTPException(503, "Semantic search not available (torch not bundled)")
    hits = search_videos(q, top_k=top_k)
    return {"query": q, "results": hits}


@router.delete("/video/{asset_id}")
def remove_video_index(asset_id: str):
    """Remove all indexed chunks for a given asset (call on video delete)."""
    delete_video_index(asset_id)
    return {"deleted": asset_id}
