"""
bg_remove_tools.py — Agent-facing LangChain tools for background removal.

Tools:
  remove_background_from_image  — removes BG from an image asset (sync)
  remove_background_from_video  — starts async BG removal for a video clip
  get_bg_remove_models          — lists available models
  check_bg_remove_job           — poll a running video job
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def get_bg_remove_models() -> str:
    """List available background removal models with their characteristics.
    Use this to help the user pick the right model before removing a background.
    Returns a summary of each model's quality, speed, and best use case.
    """
    return (
        "Available background removal models:\n"
        "  u2net    — High quality, ~180MB, medium speed. Best for general images.\n"
        "  u2netp   — Fast & small (~4MB). Good quality. Best for videos.\n"
        "  isnet    — Best quality, ~180MB, medium speed. Best for hair/fine detail.\n"
        "  silueta  — Good quality, ~43MB, fast. Best for portraits.\n\n"
        "Default for images: u2net\n"
        "Default for video:  u2netp (much faster per-frame)"
    )


@tool
def remove_background_from_image(
    input_path: str,
    model: str = "u2net",
) -> str:
    """Remove the background from a single image file and save as a transparent PNG.
    This runs synchronously and returns immediately with the output file path.

    Args:
        input_path: Absolute path to the input image (jpg, png, webp, etc.)
        model: Model to use — u2net (best), u2netp (fast), isnet (finest detail), silueta (portrait)
    
    Returns:
        Path to the output PNG with transparent background, or an error message.
    """
    import pathlib
    from backend.bg_remove.service import remove_background_image, MODELS

    if not pathlib.Path(input_path).exists():
        return f"Error: File not found: {input_path}"

    valid = list(MODELS.keys())
    if model not in valid:
        return f"Error: Unknown model '{model}'. Valid options: {valid}"

    try:
        output = remove_background_image(input_path=input_path, model_key=model)
        return (
            f"Background removed successfully!\n"
            f"Output: {output}\n"
            f"Model used: {model}\n"
            f"Format: PNG with transparent alpha channel"
        )
    except Exception as e:
        return f"Error removing background: {e}"


@tool
def remove_background_from_video(
    input_path: str,
    model: str = "u2netp",
    output_format: str = "webm",
    workers: int = 4,
) -> str:
    """Remove the background from every frame of a video file.
    This runs asynchronously — it returns a job_id immediately.
    Use check_bg_remove_job(job_id) to poll progress.
    Use check_job_status(job_id) as an alternative.

    The output video will have a transparent background (webm format)
    or green-screen compositing (mp4 format).

    Args:
        input_path: Absolute path to the input video file
        model: Model to use — u2netp (recommended for video, fast), u2net (better quality)
        output_format: 'webm' for true transparency, 'mp4' for green-screen
        workers: Number of parallel frame processing threads (1–16, default 4)

    Returns:
        job_id to poll with check_bg_remove_job(), or error message.
    """
    import pathlib
    from backend.bg_remove.service import start_video_job, MODELS

    if not pathlib.Path(input_path).exists():
        return f"Error: Video not found: {input_path}"

    valid_models = list(MODELS.keys())
    if model not in valid_models:
        return f"Error: Unknown model '{model}'. Valid: {valid_models}"

    if output_format not in ("webm", "mp4"):
        return "Error: output_format must be 'webm' or 'mp4'"

    if not (1 <= workers <= 16):
        return "Error: workers must be between 1 and 16"

    try:
        job_id = start_video_job(
            input_path=input_path,
            model_key=model,
            output_format=output_format,
            workers=workers,
        )
        return (
            f"Background removal job started!\n"
            f"Job ID: {job_id}\n"
            f"Model: {model} | Format: {output_format} | Workers: {workers}\n"
            f"Use check_bg_remove_job('{job_id}') to track progress."
        )
    except Exception as e:
        return f"Error starting job: {e}"


@tool
def check_bg_remove_job(job_id: str) -> str:
    """Check the status and progress of a background removal video job.
    
    Args:
        job_id: The job ID returned by remove_background_from_video
    
    Returns:
        Current status: pending | running (with % progress) | done (with output path) | failed | cancelled
    """
    from backend.bg_remove.service import get_job

    job = get_job(job_id)
    if not job:
        return f"Job '{job_id}' not found. It may have expired."

    status = job["status"]

    if status == "done":
        return (
            f"Job {job_id} COMPLETE!\n"
            f"Output: {job.get('output_path', 'unknown')}\n"
            f"The background has been removed from all frames."
        )
    elif status == "running":
        pct = job.get("progress", 0)
        msg = job.get("message", "")
        return f"Job {job_id} running: {pct:.0f}% — {msg}"
    elif status == "failed":
        return f"Job {job_id} FAILED: {job.get('error', 'Unknown error')}"
    elif status == "cancelled":
        return f"Job {job_id} was cancelled."
    elif status == "cancelling":
        return f"Job {job_id} is being cancelled…"
    else:
        return f"Job {job_id} status: {status} — {job.get('message', '')}"


@tool
def cancel_bg_remove_job(job_id: str) -> str:
    """Cancel a running background removal video job.
    
    Args:
        job_id: The job ID to cancel
    """
    from backend.bg_remove.service import get_job, cancel_job

    job = get_job(job_id)
    if not job:
        return f"Job '{job_id}' not found."
    if job["status"] in ("done", "failed", "cancelled"):
        return f"Job {job_id} is already {job['status']} — cannot cancel."
    cancel_job(job_id)
    return f"Cancellation requested for job {job_id}. It will stop after the current frame."


# All tools as a list for registration
BG_REMOVE_TOOLS = [
    get_bg_remove_models,
    remove_background_from_image,
    remove_background_from_video,
    check_bg_remove_job,
    cancel_bg_remove_job,
]
