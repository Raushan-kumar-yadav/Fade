 
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

AgentType  = Literal["video", "image", "audio", "pdf", "director"]
TaskStatus = Literal["pending", "running", "done", "failed", "cancelled"]


@dataclass
class AgentTask:
    id:          str
    agent_type:  AgentType
    job: str          # natural language instruction
    comp_id: str | None = None   # composition to work in
    doc_id: str | None = None   # PDF doc id
    platform: str | None = None   # platform preset name
    status: TaskStatus = "pending"
    result: str | None = None   # summary of what was done / error
    created_at:  str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at:  str | None = None
    finished_at: str | None = None


class TaskQueue:
    """Simple in-memory, asyncio-safe task queue."""

    def __init__(self) -> None:
        self._tasks:  dict[str, AgentTask] = {}
        self._lock = asyncio.Lock()

    async def push(
        self,
        agent_type: AgentType,
        job: str,
        comp_id: str | None = None,
        doc_id:  str | None = None,
        platform: str | None = None,
    ) -> str:
        task = AgentTask(
            id=str(uuid.uuid4())[:8],
            agent_type=agent_type,
            job=job,
            comp_id=comp_id,
            doc_id=doc_id,
            platform=platform,
        )
        async with self._lock:
            self._tasks[task.id] = task
        return task.id

    async def pop_pending(self, agent_type: AgentType) -> AgentTask | None:
        """Claim the first pending task of this type (marks it running)."""
        async with self._lock:
            for task in self._tasks.values():
                if task.agent_type == agent_type and task.status == "pending":
                    task.status     = "running"
                    task.started_at = datetime.utcnow().isoformat()
                    return task
        return None

    async def update(
        self,
        task_id: str,
        status: TaskStatus,
        result: str | None = None,
    ) -> None:
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status
                if result is not None:
                    self._tasks[task_id].result = result
                if status in ("done", "failed", "cancelled"):
                    self._tasks[task_id].finished_at = datetime.utcnow().isoformat()

    async def get_all(self) -> list[AgentTask]:
        async with self._lock:
            return list(self._tasks.values())

    async def clear_done(self) -> None:
        async with self._lock:
            self._tasks = {
                k: v for k, v in self._tasks.items()
                if v.status not in ("done", "failed", "cancelled")
            }

    async def summary(self) -> str:
        tasks = await self.get_all()
        if not tasks:
            return "No tasks in queue."
        lines = ["Campaign task queue:"]
        for t in tasks:
            icon = {"pending": "⏳", "running": "🔄", "done": "✅",
                    "failed": "❌", "cancelled": "🚫"}.get(t.status, "?")
            comp = f" comp={t.comp_id}" if t.comp_id else ""
            platform = f" [{t.platform}]" if t.platform else ""
            result = f" → {t.result[:60]}" if t.result else ""
            lines.append(
                f"  {icon} [{t.id}] {t.agent_type}{platform}{comp}: {t.job[:50]}{result}"
            )
        done    = sum(1 for t in tasks if t.status == "done")
        running = sum(1 for t in tasks if t.status == "running")
        pending = sum(1 for t in tasks if t.status == "pending")
        failed  = sum(1 for t in tasks if t.status == "failed")
        lines.append(
            f"\n  Total: {len(tasks)} | ✅ {done} done | 🔄 {running} running "
            f"| ⏳ {pending} pending | ❌ {failed} failed"
        )
        return "\n".join(lines)


# Singleton  
_queue: TaskQueue | None = None

def get_task_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = TaskQueue()
    return _queue
