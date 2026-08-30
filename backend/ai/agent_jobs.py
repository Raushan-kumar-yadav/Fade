from __future__ import annotations
import threading
import time

_lock = threading.Lock()
_intents: dict[str, dict] = {}
_resume_queue: list[dict] = []


def schedule(job_id: str, intent: str) -> None:
    with _lock:
        _intents[job_id] = {"intent": intent, "ts": time.time()}
    print(f"[AgentJobs] scheduled job {job_id[:8]}", flush=True)


def on_job_done(job_id: str, result: dict) -> None:
    with _lock:
        entry = _intents.pop(job_id, None)
    if entry is None:
        return
    msg = {"job_id": job_id, "intent": entry["intent"], "result": result, "ts": time.time()}
    with _lock:
        _resume_queue.append(msg)
    print(f"[AgentJobs] job {job_id[:8]} done -> resume queued", flush=True)
    try:
        from backend.events import notify
        notify("agent_resume", {"job_id": job_id, "intent": entry["intent"], **result})
    except Exception:
        pass


def pop_resume_messages() -> list[dict]:
    with _lock:
        msgs = list(_resume_queue)
        _resume_queue.clear()
    return msgs


def pending_intents() -> list[dict]:
    with _lock:
        return [{"job_id": jid, **entry} for jid, entry in _intents.items()]