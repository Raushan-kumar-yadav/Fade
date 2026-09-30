 
from __future__ import annotations
import threading
import time
import uuid

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def create_job(clip_id: str, label: str) -> dict:
    job_id = str(uuid.uuid4())[:8]
    job = {
        "job_id": job_id,
        "clip_id": clip_id,
        "label": label,
        "percent": 0,
        "current_frame": 0,
        "status": "running",
        "done": False,
        "cancelled": False,
        "error": None,
        "track_id": None,
        "started_at": time.time(),
    }
    with _lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> dict | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    with _lock:
        return list(_jobs.values())


def cancel_job(job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if job and not job["done"]:
            job["cancelled"] = True
            job["status"] = "cancelled"
            return True
    return False


def finish_job(job, track_id: str):
    job["done"] = True
    job["status"] = "done"
    job["percent"] = 100
    job["track_id"] = track_id


def fail_job(job, error: str):
    job["done"] = True
    job["status"] = "error"
    job["error"] = error
