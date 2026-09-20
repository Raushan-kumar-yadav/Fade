from __future__ import annotations
import os
import json
import time
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path
from langchain_core.tools import tool


def _db_connection_row(platform: str):
    db_path = Path(__file__).resolve().parent.parent.parent / "virality.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM connections WHERE platform=?", (platform,)
    ).fetchone()
    conn.close()
    return row


@tool
def wait_for_export(job_id: str) -> str:
    """Wait for a running export job to finish and return the output file path.

    Polls /export/progress/{job_id} every 3 seconds until done=True.
    Use immediately after export_video() so the agent blocks until the file exists.

    Args:
        job_id: Export job ID from export_video (the value after EXPORT_JOB_ID: token).

    Returns:
        String containing EXPORT_PATH:<absolute_path> on success, or an error message.
    """
    from backend.ai.tools import _get

    max_wait, elapsed, interval = 3600, 0, 3
    while elapsed < max_wait:
        try:
            data = _get(f"/export/progress/{job_id}")
        except Exception as exc:
            return f"Export poll error: {exc}"
        if data.get("error"):
            return f"Export failed: {data['error']}"
        if data.get("done"):
            path = data.get("path", "")
            if path:
                return f"Export complete!\n  Output: {path}\nEXPORT_PATH:{path}"
            return "Export done but no output path reported."
        pct = data.get("percent", 0)
        if elapsed % 30 == 0 and elapsed > 0:
            print(f"[wait_for_export] {pct}% — waiting...", flush=True)
        time.sleep(interval)
        elapsed += interval
    return "Export timed out after 60 minutes."


@tool
def post_media(
    platform: str,
    video_path: str,
    title: str = "My Video",
    description: str = "",
    tags: str = "",
    privacy: str = "public",
) -> str:
    """Upload a local video file to a connected social media platform.

    Currently supports: youtube.
    Use AFTER wait_for_export confirms the file is on disk.

    Args:
        platform: Target platform, currently youtube.
        video_path: Absolute path to the exported video file.
        title: Video title (max 100 chars).
        description: Video description (max 5000 chars).
        tags: Comma-separated tags.
        privacy: public, unlisted, or private (default public).

    Returns:
        Confirmation with VIDEO_URL:<url> on success, or an error message.
    """
    platform = platform.lower().strip()
    row = _db_connection_row(platform)
    if row is None:
        return "virality.db not found. Connect your YouTube account first."
    if not row["connected"]:
        return f"{platform.title()} not connected. Open Connections tab and sign in."
    access_token = row["access_token"]
    if not os.path.isfile(video_path):
        return f"File not found: {video_path}"

    if platform == "youtube":
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        metadata = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tag_list,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        file_size  = os.path.getsize(video_path)
        meta_bytes = json.dumps(metadata).encode("utf-8")
        init_url   = (
            "https://www.googleapis.com/upload/youtube/v3/videos"
            "?uploadType=resumable&part=snippet,status"
        )
        init_req = urllib.request.Request(
            init_url, data=meta_bytes, method="POST",
            headers={
                "Authorization":           f"Bearer {access_token}",
                "Content-Type":            "application/json; charset=UTF-8",
                "X-Upload-Content-Type":   "video/*",
                "X-Upload-Content-Length": str(file_size),
            },
        )
        try:
            with urllib.request.urlopen(init_req, timeout=30) as resp:
                upload_url = resp.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 401:
                return "YouTube token expired. Reconnect in the Connections tab."
            return f"YouTube API error {e.code}: {body[:300]}"
        except Exception as exc:
            return f"Failed to initiate upload: {exc}"
        if not upload_url:
            return "YouTube did not return an upload URL."

        CHUNK, video_id = 8 * 1024 * 1024, ""
        try:
            with open(video_path, "rb") as fh:
                offset = 0
                while offset < file_size:
                    chunk = fh.read(CHUNK)
                    end   = offset + len(chunk) - 1
                    put_req = urllib.request.Request(
                        upload_url, data=chunk, method="PUT",
                        headers={
                            "Content-Length": str(len(chunk)),
                            "Content-Range":  f"bytes {offset}-{end}/{file_size}",
                        },
                    )
                    try:
                        with urllib.request.urlopen(put_req, timeout=120) as r:
                            if r.status in (200, 201):
                                video_id = json.loads(r.read()).get("id", "")
                                break
                    except urllib.error.HTTPError as e2:
                        if e2.code == 308:
                            rng = e2.headers.get("Range", "")
                            offset = int(rng.split("-")[1]) + 1 if rng else offset + len(chunk)
                            continue
                        return f"Upload chunk error at byte {offset}: HTTP {e2.code}"
                    offset += len(chunk)
        except Exception as exc:
            return f"File read/upload error: {exc}"

        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
            return (
                f"Published to YouTube!\n"
                f"  Title:   {title}\n"
                f"  Privacy: {privacy}\n"
                f"  URL:     {url}\n"
                f"VIDEO_URL:{url}"
            )
        return "Upload done but YouTube returned no video ID."

    return f"Platform '{platform}' not yet supported. Supported: youtube."


@tool
def post_to_platform(
    platform: str = "youtube",
    format: str = "mp4-1080",
    title: str = "My Video",
    description: str = "",
    tags: str = "",
    privacy: str = "public",
) -> str:
    """Export the current Fade project and publish it to a social platform in one step.

    This is the single post-it command that orchestrates export then upload.
    Steps: (1) export timeline to project folder, (2) wait for completion, (3) upload.

    Use when user says: post it to YouTube, upload my video, publish to YouTube,
    export and upload, share to YouTube now.

    Args:
        platform: Social platform, currently youtube.
        format: Export format, one of mp4-1080, mp4-4k, mp4-720, shorts, reels, webm, gif.
        title: Video title on the platform.
        description: Video description or caption.
        tags: Comma-separated tags.
        privacy: public, unlisted, or private (default public).

    Returns:
        Final status message with the published URL or error.
    """
    from backend.ai.tools import _post
    from backend.state import engine

    _DIMS = {
        "mp4-1080": (1920, 1080), "mp4-4k": (3840, 2160), "mp4-720": (1280, 720),
        "shorts": (1080, 1920), "reels": (1080, 1920),
        "webm": (1920, 1080), "gif": (854, 480),
    }
    _EXT  = {
        "mp4-1080": "mp4", "mp4-4k": "mp4", "mp4-720": "mp4",
        "shorts": "mp4", "reels": "mp4", "webm": "webm", "gif": "gif",
    }
    _FMAP = {
        "shorts": "shorts", "reels": "reels", "mp4": "mp4-1080",
        "4k": "mp4-4k", "720p": "mp4-720", "1080p": "mp4-1080",
        "webm": "webm", "gif": "gif",
    }
    key    = format.lower().strip()
    fmt_id = _FMAP.get(key, key)
    if fmt_id not in _DIMS:
        fmt_id = "mp4-1080"
    w, h = _DIMS[fmt_id]
    ext  = _EXT.get(fmt_id, "mp4")

    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:40].strip()
    base = f"{safe or 'Fade_export'}.{ext}"
    proj_file = getattr(engine.project, "filePath", None) if engine.project else None
    if proj_file:
        output_path = os.path.join(os.path.dirname(proj_file), base)
    else:
        output_path = os.path.join(os.getcwd(), base)

    body = {
        "outputPath": output_path,
        "width": w, "height": h, "fps": 30.0,
        "codec": "auto", "videoBitrate": "8M", "crf": 22, "preset": "medium",
        "audioBitrate": "192k", "audioSampleRate": 48000, "audioChannels": 2,
        "formatId": fmt_id,
    }
    try:
        result = _post("/export/start", body)
    except Exception as exc:
        return f"Could not start export: {exc}"

    job_id = result.get("jobId", "")
    total  = result.get("total", 0)
    if not job_id:
        return "Export start returned no job ID."

    print(
        f"[post_to_platform] Export started -> {output_path} "
        f"| {fmt_id} {w}x{h} | {total} frames",
        flush=True,
    )

    wait_result = wait_for_export.invoke({"job_id": job_id})
    if not any(wait_result.startswith(p) for p in ("Export complete", "EXPORT_PATH")):
        return f"Export failed before upload.\n{wait_result}"

    final_path = output_path
    for line in wait_result.splitlines():
        if line.startswith("EXPORT_PATH:"):
            final_path = line[len("EXPORT_PATH:"):]
            break

    upload = post_media.invoke({
        "platform": platform, "video_path": final_path,
        "title": title, "description": description,
        "tags": tags, "privacy": privacy,
    })
    return f"Export done -> {final_path}\n\n{upload}"


PUBLISH_TOOLS = [wait_for_export, post_media, post_to_platform]
