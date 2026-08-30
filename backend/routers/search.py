from fastapi import APIRouter, Query
from ..ai.VideoSemantic.indexer import search_videos, delete_video_index

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
    hits = search_videos(q, top_k=top_k)
    return {"query": q, "results": hits}


@router.delete("/video/{asset_id}")
def remove_video_index(asset_id: str):
    """Remove all indexed chunks for a given asset (call on video delete)."""
    delete_video_index(asset_id)
    return {"deleted": asset_id}
