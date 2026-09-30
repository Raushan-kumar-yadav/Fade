
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Literal, AsyncIterator, Optional


#   Per-comp tool sets  

def _build_tool_set(comp_type: str) -> list:
    """Return the appropriate filtered tool list for a comp type."""
    from backend.ai.tools import ALL_TOOLS

    _IMAGE_NAMES = {
        "get_timeline_state", "get_library", "get_library_assets",
        "place_clip", "add_text_clip", "add_shape_clip", "add_solid_clip",
        "update_clip", "set_clip_param", "bulk_update_clips",
        "add_effect", "remove_effect", "set_effect_param",
        "apply_effect_to_clip", "patch_clip_effect",
        "get_effects_catalog", "list_effects_catalog",
        "create_composition", "list_compositions", "activate_comp",
        "get_comp_state", "add_clip_to_comp",
        "generate_image", "find_free_overlay_track", "add_track",
        "get_selected_clip", "describe_clip", "describe_selected_clip",
        "animate_property", "apply_curve_preset",
        "download_images", "undo", "redo",
        "get_current_viewport_image", "get_comp_about", "get_clip_about",
    }
    _VIDEO_NAMES = _IMAGE_NAMES | {
        "split_clip", "trim_clip", "move_clip", "reposition_clip", "delete_clip",
        "add_transition", "add_transitions_between_all_clips",
        "get_transitions_catalog",
        "generate_captions", "remove_silence", "generate_tts",
        "download_videos", "search_news",
    }
    _PDF_NAMES = _IMAGE_NAMES | {
        "download_images", "search_news",
        "create_pdf_doc", "list_pdf_docs", "list_pdf_pages",
        "add_pdf_page", "delete_pdf_page", "reorder_pdf_pages",
        "get_pdf_page_summary", "get_pdf_doc_summary",
    }

    name_set = {"image": _IMAGE_NAMES, "video": _VIDEO_NAMES, "pdf": _PDF_NAMES}.get(
        comp_type, None
    )
    if name_set is None:
        return ALL_TOOLS
    return [t for t in ALL_TOOLS if getattr(t, "name", None) in name_set]


#   Comp-scoped system prompt  

def _comp_system(comp_type: str, comp_id: str, intent: str) -> str:
    labels = {
        "image": ("IMAGE AGENT", "social image poster", "kind=image"),
        "video": ("VIDEO AGENT", "short video (30-60s) with effects, transitions, and captions", "kind=video"),
        "pdf":   ("PDF AGENT",  "multi-page PDF document / carousel", "kind=pdf"),
    }
    name, desc, kind = labels.get(comp_type, ("AGENT", "composition", ""))
    return (
        f"[DIRECTOR] You are the {name}. "
        f"Your ONLY job is to create a {desc} inside composition ID={comp_id!r} ({kind}). "
        f"Do NOT touch any other composition or the root timeline. "
        f"FIRST call activate_comp(comp_id={comp_id!r}) to switch to it, "
        f"then build the content. "
        f"Target goal: {intent}"
    )


def _split_intent(intent: str, assets: list[str]) -> dict[str, str]:
    """Rule-based split — no extra LLM call needed."""
    asset_str = ", ".join(assets[:8]) or "provided assets"
    return {
        "image": (
            f"Create a high-quality social media image poster using: {asset_str}. "
            f"Overall goal: {intent}"
        ),
        "video": (
            f"Edit a polished 30-60s video with effects, transitions, and captions "
            f"using: {asset_str}. Overall goal: {intent}"
        ),
        "pdf": (
            f"Create a branded multi-page PDF document / carousel "
            f"using: {asset_str}. Overall goal: {intent}"
        ),
    }


#   Tool labels for SSE  

_TOOL_LABELS: dict[str, str] = {
    "get_timeline_state": "Reading timeline…",
    "get_library": "Scanning library…",
    "get_library_assets": "Scanning library…",
    "place_clip": "Placing clip…",
    "add_text_clip": "Adding text…",
    "add_shape_clip": "Drawing shape…",
    "add_solid_clip": "Adding solid…",
    "split_clip": "Splitting clip…",
    "trim_clip": "Trimming clip…",
    "move_clip": "Moving clip…",
    "delete_clip": "Deleting clip…",
    "add_transition": "Adding transition…",
    "apply_effect_to_clip": "Applying effect…",
    "generate_image": "Generating image…",
    "generate_captions": "Generating captions…",
    "remove_silence": "Removing silence…",
    "download_videos": "Downloading footage…",
    "download_images": "Downloading images…",
    "animate_property": "Animating…",
    "activate_comp": "Switching comp…",
    "create_composition": "Creating comp…",
    "add_clip_to_comp": "Adding to comp…",
    "generate_tts": "Generating voice…",
    "describe_clip": "Inspecting clip…",
    "find_free_overlay_track": "Finding overlay track…",
    "get_current_viewport_image": "Checking viewport…",
    "get_comp_about": "Reading comp…",
    "get_clip_about": "Inspecting clip…",
}


#   Shared Scratchpad  

@dataclass
class AgentScratchpad:
    """Shared mutable state visible to all agents in a session.

    Each agent reads this at startup and after significant actions to stay
    aware of what peers have done and what timeline ranges are occupied.
    """
    # Per-agent status summaries, keyed by comp_type
    agent_status: dict[str, str] = field(default_factory=dict)
    # Occupied timeline ranges 
    placed_ranges: list[dict] = field(default_factory=list)
    # Free-form notes any agent can write for peers
    notes: list[str] = field(default_factory=list)

    def update_status(self, comp_type: str, status: str) -> None:
        self.agent_status[comp_type] = status

    def add_placed(self, comp_type: str, track: str, start: int, end: int, desc: str = "") -> None:
        self.placed_ranges.append({
            "agent": comp_type,
            "track": track,
            "start": start,
            "end": end,
            "desc": desc,
        })

    def add_note(self, comp_type: str, note: str) -> None:
        self.notes.append(f"[{comp_type.upper()}] {note}")
        # Keep at most 10 notes to avoid bloating prompt
        if len(self.notes) > 10:
            self.notes = self.notes[-10:]

    def render(self, viewer_type: str) -> str:
        """Render a compact context block for injection into an agent's system prompt."""
        lines = ["=== PEER AGENT STATUS (read-only) ==="]

        # Other agents' statuses
        for atype, status in self.agent_status.items():
            if atype != viewer_type:
                lines.append(f"  {atype.upper()} AGENT: {status}")

        # Occupied ranges
        others = [r for r in self.placed_ranges if r["agent"] != viewer_type]
        if others:
            lines.append("Occupied timeline ranges (avoid collisions):")
            for r in others[-8:]:  # last 8 to bound length
                lines.append(
                    f"  [{r['agent']}] track={r['track']} "
                    f"frames {r['start']}-{r['end']}"
                    + (f" ({r['desc']})" if r["desc"] else "")
                )

        # Peer notes
        if self.notes:
            lines.append("Peer notes:")
            for n in self.notes:
                lines.append(f"  {n}")

        lines.append("=== END PEER STATUS ===")
        return "\n".join(lines)


#   Agent job  

@dataclass
class AgentJob:
    job_id: str
    comp_type: str
    comp_id: str
    intent: str
    status: str = "pending"   # pending | running | done | error
    error: str = ""
    result: dict = field(default_factory=dict)
    task: Optional[asyncio.Task] = None


#   Session registry  

@dataclass
class DirectorSession:
    session_id: str
    jobs: list[AgentJob] = field(default_factory=list)
    cancelled:  bool = False
    scratchpad: AgentScratchpad = field(default_factory=AgentScratchpad)


_sessions: dict[str, DirectorSession] = {}


def get_session(session_id: str) -> Optional[DirectorSession]:
    return _sessions.get(session_id)


#   Scratchpad parsing helpers  

def _parse_placed_from_tool_result(comp_type: str, tool_name: str, result_str: str,
                                   scratchpad: AgentScratchpad) -> None:
    """
    Best-effort: extract track/frame placement info from tool result strings
    so peers can see what this agent placed.
    """
    import re
    if tool_name not in ("place_clip", "add_text_clip", "add_shape_clip",
                         "add_solid_clip", "add_clip_to_comp", "move_clip"):
        return
    # Try to parse "startFrame=N … durationFrames=M" or "start=N end=M"
    start_m = re.search(r'startFrame[=:]\s*(\d+)', result_str)
    dur_m   = re.search(r'durationFrames[=:]\s*(\d+)', result_str, re.IGNORECASE)
    end_m   = re.search(r'endFrame[=:]\s*(\d+)', result_str, re.IGNORECASE)
    track_m = re.search(r'track(?:Index)?[=:]\s*(\d+|\w+)', result_str, re.IGNORECASE)

    start = int(start_m.group(1)) if start_m else 0
    if end_m:
        end = int(end_m.group(1))
    elif dur_m:
        end = start + int(dur_m.group(1))
    else:
        end = start + 90  # fallback 3s at 30fps

    track = track_m.group(1) if track_m else "?"
    scratchpad.add_placed(comp_type, track, start, end, desc=tool_name)


#   Per-agent async runner  

async def _run_agent_job(job: AgentJob, port: int, session: DirectorSession) -> None:
    from backend.events import notify
    from backend.ai.agent import build_agent
    from langchain_core.messages import HumanMessage

    tools = _build_tool_set(job.comp_type)
    sys_ctx = _comp_system(job.comp_type, job.comp_id, job.intent)
    tool_count = 0
    sp         = session.scratchpad

    def _emit(phase: str, label: str, progress: int = 0, **extra):
        notify("agent_progress", {
            "session_id": session.session_id,
            "job_id": job.job_id,
            "comp_type":  job.comp_type,
            "comp_id": job.comp_id,
            "phase": phase,
            "label": label,
            "progress": progress,
            **extra,
        })

    # Mark self as starting in shared scratchpad
    sp.update_status(job.comp_type, "starting")

    _emit("start", f"Starting {job.comp_type} agent…")
    job.status = "running"

     
    def _get_peer_ctx() -> str:
        return sp.render(viewer_type=job.comp_type)

    try:
        graph  = build_agent(port=port, tools_override=tools,
                             system_override=sys_ctx,
                             scratchpad_fn=_get_peer_ctx)
        config = {"recursion_limit": 80}

         
        peer_ctx_initial = _get_peer_ctx()
        initial_content = job.intent
        if peer_ctx_initial.strip() != "=== PEER AGENT STATUS (read-only) ===\n=== END PEER STATUS ===":
            initial_content = f"{peer_ctx_initial}\n\n--- YOUR TASK ---\n{job.intent}"

        state = {"messages": [HumanMessage(content=initial_content)]}

        sp.update_status(job.comp_type, "running")

        async for event in graph.astream_events(state, config=config, version="v2"):
            if session.cancelled:
                job.status = "error"
                job.error  = "Cancelled"
                _emit("cancelled", "Cancelled")
                sp.update_status(job.comp_type, "cancelled")
                return

            kind = event.get("event", "")
            data = event.get("data", {})

            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                token = (chunk.content if chunk and isinstance(getattr(chunk, "content", ""), str) else "")
                if token:
                    _emit("thinking", "Thinking…",
                          progress=min(90, tool_count * 10), token=token)

            elif kind == "on_tool_start":
                tool_name  = event.get("name", "")
                tool_count += 1
                sp.update_status(job.comp_type,
                                 f"running ({tool_count} tools, last: {tool_name})")
                _emit("tool", _TOOL_LABELS.get(tool_name, f"Running {tool_name}…"),
                      progress=min(90, tool_count * 10), tool=tool_name)

            elif kind == "on_tool_end":
                tool_name   = event.get("name", "")
                tool_output = str(data.get("output", ""))
                # Parse placement data from the result so peers are aware
                _parse_placed_from_tool_result(
                    job.comp_type, tool_name, tool_output, sp
                )

        job.status = "done"
        sp.update_status(job.comp_type, "done")
        sp.add_note(job.comp_type, f"Finished. Placed {len([r for r in sp.placed_ranges if r['agent']==job.comp_type])} clips.")
        _emit("done", f"{job.comp_type.capitalize()} agent finished ✓", progress=100)
        print(f"[Director] {job.comp_type} agent done (comp={job.comp_id[:8]})", flush=True)

    except Exception as exc:
        job.status = "error"
        job.error  = str(exc)
        sp.update_status(job.comp_type, f"error: {exc}")
        _emit("error", f"Error: {exc}")
        print(f"[Director] {job.comp_type} agent ERROR: {exc}", flush=True)


#   Director  

class Director:
    """Launch and coordinate parallel agents for image, video, and PDF comps."""

    async def run(
        self,
        assets: list[str],
        intent: str,
        port: int = 8000,
        comp_types: list[str] | None = None,
        publish_after: bool = False,
    ) -> AsyncIterator[dict]:
        from backend.state import engine
        from backend.events import notify

        if comp_types is None:
            comp_types = ["image", "video", "pdf"]

        session_id = str(uuid.uuid4())
        session    = DirectorSession(session_id=session_id)
        _sessions[session_id] = session

        sub_intents = _split_intent(intent, assets)

        _DIM: dict[str, tuple[int, int]] = {
            "image": (1080, 1080),
            "video": (1920, 1080),
            "pdf": (2480, 3508),
        }

        for ctype in comp_types:
            if engine.project is None:
                yield {"error": "No active project"}
                return
            w, h = _DIM.get(ctype, (1920, 1080))
            comp      = engine.createComposition(
                name=f"Director — {ctype.capitalize()}",
                width=w, height=h, fps=30, total_frames=300,
            )
            comp.kind      = ctype
            comp.isHidden  = False
            comp.isDefault = False
            job = AgentJob(
                job_id=str(uuid.uuid4()),
                comp_type=ctype,
                comp_id=comp.timelineId,
                intent=sub_intents.get(ctype, intent),
            )
            session.jobs.append(job)
            # Pre-register in scratchpad so peers know who exists
            session.scratchpad.update_status(ctype, "pending")

        notify("comps", {})

        yield {
            "type":       "session_created",
            "session_id": session_id,
            "jobs": [
                {"job_id": j.job_id, "comp_type": j.comp_type, "comp_id": j.comp_id}
                for j in session.jobs
            ],
        }

        # Launch all agents concurrently
        for job in session.jobs:
            job.task = asyncio.create_task(
                _run_agent_job(job, port=port, session=session)
            )

        await asyncio.gather(*[j.task for j in session.jobs], return_exceptions=True)

        done_n  = sum(1 for j in session.jobs if j.status == "done")
        error_n = sum(1 for j in session.jobs if j.status == "error")

        yield {
            "type": "all_done",
            "session_id": session_id,
            "done": done_n,
            "errors": error_n,
            "jobs": [
                {"job_id": j.job_id, "comp_type": j.comp_type,
                 "comp_id": j.comp_id, "status": j.status, "error": j.error}
                for j in session.jobs
            ],
        }

        notify("agent_progress", {
            "session_id": session_id,
            "phase": "all_done",
            "label": f"All agents finished — {done_n} done, {error_n} errors",
            "progress": 100,
        })

    def cancel(self, session_id: str) -> bool:
        session = _sessions.get(session_id)
        if session is None:
            return False
        session.cancelled = True
        for job in session.jobs:
            if job.task and not job.task.done():
                job.task.cancel()
        print(f"[Director] Session {session_id[:8]} cancelled.", flush=True)
        return True

    def status(self, session_id: str) -> dict | None:
        session = _sessions.get(session_id)
        if session is None:
            return None
        return {
            "session_id": session_id,
            "cancelled":  session.cancelled,
            "scratchpad": {
                "agent_status":  session.scratchpad.agent_status,
                "placed_ranges": session.scratchpad.placed_ranges,
                "notes":         session.scratchpad.notes,
            },
            "jobs": [
                {"job_id": j.job_id, "comp_type": j.comp_type,
                 "comp_id": j.comp_id, "status": j.status, "error": j.error}
                for j in session.jobs
            ],
        }
