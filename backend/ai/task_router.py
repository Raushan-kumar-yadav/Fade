 
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.ai import task_store as _store

task_router = APIRouter(prefix="/ai/plans", tags=["ai-plans"])


#   List plans  

@task_router.get("")
def list_plans(limit: int = 20):
    plans = _store.list_plans(limit=limit)
    return {"plans": [p.to_dict() for p in plans]}


#   Get single plan  

@task_router.get("/{plan_id}")
def get_plan(plan_id: str):
    plan = _store.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    return plan.to_dict()


#   Get active plan  

@task_router.get("/active/current")
def get_active_plan():
    plan = _store.get_active_plan()
    if not plan:
        return {"plan": None, "message": "No active plan"}
    return {"plan": plan.to_dict()}


#   Pause plan  

@task_router.post("/{plan_id}/pause")
def pause_plan(plan_id: str):
    plan = _store.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    if plan.status not in ("executing", "planning"):
        raise HTTPException(400, f"Cannot pause plan in '{plan.status}' state")
    _store.update_plan_status(plan_id, "paused")
    return {"ok": True, "status": "paused"}


#   Resume plan  

@task_router.post("/{plan_id}/resume")
def resume_plan(plan_id: str):
    plan = _store.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    if plan.status != "paused":
        raise HTTPException(400, f"Cannot resume plan in '{plan.status}' state")
    _store.update_plan_status(plan_id, "executing")
    return {"ok": True, "status": "executing"}


#   Cancel plan  

@task_router.post("/{plan_id}/cancel")
def cancel_plan(plan_id: str):
    plan = _store.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
 
    for step in plan.steps:
        if step.status in ("pending", "running"):
            _store.update_step_status(step.step_id, "skipped")
    _store.update_plan_status(plan_id, "failed")
    return {"ok": True, "status": "cancelled"}


#   Delete plan  

@task_router.delete("/{plan_id}")
def delete_plan(plan_id: str):
    deleted = _store.delete_plan(plan_id)
    if not deleted:
        raise HTTPException(404, f"Plan {plan_id} not found")
    return {"ok": True}


# Step management endpoints  

@task_router.post("/steps/{step_id}/skip")
def skip_step(step_id: str):
    """Mark a step as skipped."""
    ok = _store.skip_step(step_id)
    if not ok:
        raise HTTPException(400, "Could not skip step — it may be running or already done")
    return {"ok": True, "step_id": step_id, "status": "skipped"}


@task_router.post("/steps/{step_id}/retry")
def retry_step(step_id: str):
    """Reset a failed/skipped step back to pending."""
    ok = _store.reset_step(step_id)
    if not ok:
        raise HTTPException(400, "Could not retry step — it may be running")
    return {"ok": True, "step_id": step_id, "status": "pending"}


class InsertStepRequest(BaseModel):
    after_order: int
    description: str
    tool_name: str = ""


@task_router.post("/{plan_id}/steps/insert")
def insert_step(plan_id: str, req: InsertStepRequest):
    """Insert a new step into an existing plan."""
    plan = _store.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    step = _store.insert_step(plan_id, req.after_order, req.description, req.tool_name)
    return {"ok": True, "step_id": step.step_id, "order": step.order}


class EditStepRequest(BaseModel):
    description: str = ""
    tool_name: str = ""


@task_router.patch("/steps/{step_id}")
def edit_step(step_id: str, req: EditStepRequest):
    """Edit a pending step's description or tool name."""
    ok = _store.edit_step(step_id,
                          description=req.description or None,
                          tool_name=req.tool_name or None)
    if not ok:
        raise HTTPException(400, "Could not edit step — it may already be running or done")
    return {"ok": True, "step_id": step_id}
