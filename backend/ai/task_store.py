 
from __future__ import annotations
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# Data classes  

@dataclass
class TaskStep:
    step_id: str
    plan_id: str
    order: int
    description: str
    tool_name: str = ""
    depends_on: str | None = None
    status: str = "pending"      # pending | running | done | skipped | failed
    result: str | None = None    # JSON string of tool output
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None


@dataclass
class TaskPlan:
    plan_id: str
    goal: str
    status: str = "planning"     # planning | executing | paused | done | failed
    agent_type: str = "video"
    created_at: float = 0.0
    updated_at: float = 0.0
    steps: list[TaskStep] = field(default_factory=list)

    # ── Derived helpers ──────────────────────────────────────────────────
    @property
    def progress(self) -> dict:
        total = len(self.steps)
        done = sum(1 for s in self.steps if s.status == "done")
        failed = sum(1 for s in self.steps if s.status == "failed")
        running = sum(1 for s in self.steps if s.status == "running")
        return {
            "total": total,
            "done": done,
            "failed": failed,
            "running": running,
            "pending": total - done - failed - running,
            "percent": int(done / total * 100) if total > 0 else 0,
        }

    @property
    def next_pending_step(self) -> TaskStep | None:
        for s in sorted(self.steps, key=lambda x: x.order):
            if s.status == "pending":
                # Check dependency
                if s.depends_on:
                    dep = next((x for x in self.steps if x.step_id == s.depends_on), None)
                    if dep and dep.status != "done":
                        continue  # dependency not met, skip for now
                return s
        return None

    def to_dict(self) -> dict:
        d = {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "status": self.status,
            "agent_type": self.agent_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "progress": self.progress,
            "steps": [
                {
                    "step_id": s.step_id,
                    "order": s.order,
                    "description": s.description,
                    "tool_name": s.tool_name,
                    "status": s.status,
                    "error": s.error,
                }
                for s in sorted(self.steps, key=lambda x: x.order)
            ],
        }
        return d


# ── Store ────────────────────────────────────────────────────────────────────

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "fade_tasks.db"
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db():
    """Create tables if they don't exist."""
    with _lock:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS task_plans (
                plan_id    TEXT PRIMARY KEY,
                goal       TEXT NOT NULL,
                status     TEXT DEFAULT 'planning',
                agent_type TEXT DEFAULT 'video',
                created_at REAL,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS task_steps (
                step_id     TEXT PRIMARY KEY,
                plan_id     TEXT REFERENCES task_plans(plan_id) ON DELETE CASCADE,
                "order"     INTEGER,
                description TEXT,
                tool_name   TEXT DEFAULT '',
                depends_on  TEXT,
                status      TEXT DEFAULT 'pending',
                result      TEXT,
                error       TEXT,
                started_at  REAL,
                finished_at REAL
            );

            CREATE INDEX IF NOT EXISTS idx_steps_plan
                ON task_steps(plan_id);
        """)
        conn.commit()
        conn.close()
        print(f"[TaskStore] DB initialized: {_DB_PATH}", flush=True)


# Init on import
_init_db()


# ── CRUD ─────────────────────────────────────────────────────────────────────

def create_plan(goal: str, agent_type: str = "video") -> TaskPlan:
    """Create a new empty plan."""
    plan = TaskPlan(
        plan_id=str(uuid.uuid4())[:12],
        goal=goal,
        status="planning",
        agent_type=agent_type,
        created_at=time.time(),
        updated_at=time.time(),
    )
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO task_plans (plan_id, goal, status, agent_type, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (plan.plan_id, plan.goal, plan.status, plan.agent_type,
             plan.created_at, plan.updated_at),
        )
        conn.commit()
        conn.close()
    print(f"[TaskStore] Plan created: {plan.plan_id} -- {goal[:60]}", flush=True)
    return plan


def add_step(
    plan_id: str,
    description: str,
    tool_name: str = "",
    order: int = 0,
    depends_on: str | None = None,
) -> TaskStep:
    """Add a step to an existing plan."""
    step = TaskStep(
        step_id=str(uuid.uuid4())[:12],
        plan_id=plan_id,
        order=order,
        description=description,
        tool_name=tool_name,
        depends_on=depends_on,
    )
    with _lock:
        conn = _get_conn()
        conn.execute(
            'INSERT INTO task_steps (step_id, plan_id, "order", description, tool_name, '
            "depends_on, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (step.step_id, step.plan_id, step.order, step.description,
             step.tool_name, step.depends_on, step.status),
        )
        conn.execute(
            "UPDATE task_plans SET updated_at=? WHERE plan_id=?",
            (time.time(), plan_id),
        )
        conn.commit()
        conn.close()
    return step


def update_step_status(
    step_id: str,
    status: str,
    result: str | None = None,
    error: str | None = None,
) -> None:
    """Update a step's status and optional result/error."""
    now = time.time()
    with _lock:
        conn = _get_conn()
        if status == "running":
            conn.execute(
                "UPDATE task_steps SET status=?, started_at=? WHERE step_id=?",
                (status, now, step_id),
            )
        elif status in ("done", "failed", "skipped"):
            conn.execute(
                "UPDATE task_steps SET status=?, result=?, error=?, finished_at=? "
                "WHERE step_id=?",
                (status, result, error, now, step_id),
            )
        else:
            conn.execute(
                "UPDATE task_steps SET status=? WHERE step_id=?",
                (status, step_id),
            )
        # Update plan timestamp
        row = conn.execute(
            "SELECT plan_id FROM task_steps WHERE step_id=?", (step_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE task_plans SET updated_at=? WHERE plan_id=?",
                (now, row["plan_id"]),
            )
        conn.commit()
        conn.close()
    print(f"[TaskStore] Step {step_id} -> {status}", flush=True)


def update_plan_status(plan_id: str, status: str) -> None:
    """Update a plan's overall status."""
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE task_plans SET status=?, updated_at=? WHERE plan_id=?",
            (status, time.time(), plan_id),
        )
        conn.commit()
        conn.close()
    print(f"[TaskStore] Plan {plan_id} -> {status}", flush=True)


def get_plan(plan_id: str) -> TaskPlan | None:
    """Load a plan with all its steps."""
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM task_plans WHERE plan_id=?", (plan_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None
        plan = TaskPlan(
            plan_id=row["plan_id"],
            goal=row["goal"],
            status=row["status"],
            agent_type=row["agent_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        step_rows = conn.execute(
            'SELECT * FROM task_steps WHERE plan_id=? ORDER BY "order"',
            (plan_id,),
        ).fetchall()
        for sr in step_rows:
            plan.steps.append(TaskStep(
                step_id=sr["step_id"],
                plan_id=sr["plan_id"],
                order=sr["order"],
                description=sr["description"],
                tool_name=sr["tool_name"] or "",
                depends_on=sr["depends_on"],
                status=sr["status"],
                result=sr["result"],
                error=sr["error"],
                started_at=sr["started_at"],
                finished_at=sr["finished_at"],
            ))
        conn.close()
    return plan


def get_active_plan() -> TaskPlan | None:
    """Return the most recent non-done plan (executing or paused)."""
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT plan_id FROM task_plans "
            "WHERE status IN ('planning', 'executing', 'paused') "
            "ORDER BY updated_at DESC LIMIT 1",
        ).fetchone()
        conn.close()
    if row:
        return get_plan(row["plan_id"])
    return None


def list_plans(limit: int = 20) -> list[TaskPlan]:
    """List recent plans (summary only, no step results)."""
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT plan_id FROM task_plans ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
    plans = []
    for r in rows:
        p = get_plan(r["plan_id"])
        if p:
            plans.append(p)
    return plans


def delete_plan(plan_id: str) -> bool:
    """Delete a plan and all its steps."""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM task_steps WHERE plan_id=?", (plan_id,))
        cur = conn.execute("DELETE FROM task_plans WHERE plan_id=?", (plan_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
    if deleted:
        print(f"[TaskStore] Plan {plan_id} deleted", flush=True)
    return deleted


# ── Plan management helpers ────────────────────────────────────────────────────

def skip_step(step_id: str) -> bool:
    """Mark a step as skipped (bypasses execution)."""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE task_steps SET status='skipped', finished_at=? WHERE step_id=? "
            "AND status IN ('pending', 'failed')",
            (time.time(), step_id),
        )
        if cur.rowcount:
            row = conn.execute("SELECT plan_id FROM task_steps WHERE step_id=?", (step_id,)).fetchone()
            if row:
                conn.execute("UPDATE task_plans SET updated_at=? WHERE plan_id=?",
                             (time.time(), row["plan_id"]))
        conn.commit()
        conn.close()
    print(f"[TaskStore] Step {step_id} skipped", flush=True)
    return cur.rowcount > 0


def reset_step(step_id: str) -> bool:
    """Reset a failed/skipped step back to pending so it can be retried."""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE task_steps SET status='pending', error=NULL, result=NULL, "
            "started_at=NULL, finished_at=NULL WHERE step_id=? "
            "AND status IN ('failed', 'skipped', 'done')",
            (step_id,),
        )
        if cur.rowcount:
            row = conn.execute("SELECT plan_id FROM task_steps WHERE step_id=?", (step_id,)).fetchone()
            if row:
                conn.execute("UPDATE task_plans SET updated_at=? WHERE plan_id=?",
                             (time.time(), row["plan_id"]))
        conn.commit()
        conn.close()
    print(f"[TaskStore] Step {step_id} reset to pending", flush=True)
    return cur.rowcount > 0


def insert_step(plan_id: str, after_order: int, description: str,
                tool_name: str = "") -> TaskStep:
    """Insert a new step after a given order index, shifting later steps up."""
    with _lock:
        conn = _get_conn()
        # Shift existing steps with order > after_order
        conn.execute(
            'UPDATE task_steps SET "order"="order"+1 WHERE plan_id=? AND "order">?',
            (plan_id, after_order),
        )
        new_order = after_order + 1
        step_id = str(uuid.uuid4())[:12]
        conn.execute(
            'INSERT INTO task_steps (step_id, plan_id, "order", description, tool_name, status) '
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (step_id, plan_id, new_order, description, tool_name),
        )
        conn.execute("UPDATE task_plans SET updated_at=? WHERE plan_id=?",
                     (time.time(), plan_id))
        conn.commit()
        conn.close()
    print(f"[TaskStore] Inserted step {step_id} at order {new_order}", flush=True)
    return TaskStep(step_id=step_id, plan_id=plan_id, order=new_order,
                    description=description, tool_name=tool_name)


def edit_step(step_id: str, description: str | None = None,
              tool_name: str | None = None) -> bool:
    """Edit a pending step's description and/or tool name."""
    with _lock:
        conn = _get_conn()
        if description and tool_name:
            cur = conn.execute(
                "UPDATE task_steps SET description=?, tool_name=? WHERE step_id=? AND status='pending'",
                (description, tool_name, step_id),
            )
        elif description:
            cur = conn.execute(
                "UPDATE task_steps SET description=? WHERE step_id=? AND status='pending'",
                (description, step_id),
            )
        elif tool_name:
            cur = conn.execute(
                "UPDATE task_steps SET tool_name=? WHERE step_id=? AND status='pending'",
                (tool_name, step_id),
            )
        else:
            conn.close()
            return False
        conn.commit()
        conn.close()
    return cur.rowcount > 0


def pause_plan(plan_id: str) -> bool:
    """Pause an executing or planning plan (executor checks this before each step)."""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE task_plans SET status='paused', updated_at=? WHERE plan_id=? "
            "AND status IN ('executing', 'planning')",
            (time.time(), plan_id),
        )
        conn.commit()
        conn.close()
    print(f"[TaskStore] Plan {plan_id} paused", flush=True)
    return cur.rowcount > 0


def resume_plan(plan_id: str) -> bool:
    """Resume a paused plan."""
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE task_plans SET status='executing', updated_at=? WHERE plan_id=? AND status='paused'",
            (time.time(), plan_id),
        )
        conn.commit()
        conn.close()
    print(f"[TaskStore] Plan {plan_id} resumed", flush=True)
    return cur.rowcount > 0
