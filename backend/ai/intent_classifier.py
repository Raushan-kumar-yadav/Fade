 
from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.ai.skill_loader import SkillDef


class Intent(str, Enum):
    SIMPLE_EDIT   = "simple_edit"      # single tool call, direct execution
    SIMPLE_QUERY  = "simple_query"     # read-only question
    COMPLEX_TASK  = "complex_task"     # multi-step, needs planning
    CONTINUE_TASK = "continue_task"    # resume active plan
    CHECK_PROGRESS = "check_progress"  # show plan status
    CANCEL_TASK   = "cancel_task"      # cancel active plan


# Signals that indicate multi-step complexity
_COMPLEXITY_SIGNALS = [
    "and then", "after that", "also add", "then add",
    "create a video", "make a video", "build a video",
    "make a", "build a", "create a",
    "with captions", "with music", "with voiceover",
    "with transitions", "with effects", "with text",
    "step by step", "full video", "complete video",
    "news video", "montage", "compilation",
    "download and place", "search and add",
    "multiple clips", "several scenes",
]

# Signals for continue/resume
_CONTINUE_SIGNALS = [
    "continue", "keep going", "next step", "go ahead",
    "resume", "proceed", "carry on", "do it", "go on",
]

# Signals for checking progress
_PROGRESS_SIGNALS = [
    "show plan", "what's left", "progress", "status",
    "how far", "how's it going", "show steps", "what's the plan",
    "show todo", "show tasks",
]

# Signals for cancellation
_CANCEL_SIGNALS = [
    "cancel plan", "stop plan", "abort plan", "start over",
    "forget the plan", "scrap it", "cancel task", "delete plan",
    "new plan", "reset plan",
]


def classify_intent(message: str, has_active_plan: bool = False) -> Intent:
    """Classify user message intent using rule-based heuristics.
    
    Zero LLM cost -- handles 90%+ of cases with simple string matching.
    """
    msg = message.lower().strip()

    # Short continue commands (only if there's an active plan)
    if has_active_plan:
        if msg in ("continue", "next", "go", "yes", "ok", "proceed", "do it"):
            return Intent.CONTINUE_TASK
        for signal in _CONTINUE_SIGNALS:
            if signal in msg:
                return Intent.CONTINUE_TASK

    # Progress check
    for signal in _PROGRESS_SIGNALS:
        if signal in msg:
            return Intent.CHECK_PROGRESS

    # Cancellation
    for signal in _CANCEL_SIGNALS:
        if signal in msg:
            return Intent.CANCEL_TASK

    # Complexity detection: count how many complexity signals match
    hits = sum(1 for s in _COMPLEXITY_SIGNALS if s in msg)
    
    # Also check for long messages with action verbs (likely complex)
    word_count = len(msg.split())
    has_multiple_verbs = sum(1 for v in [
        "add", "place", "create", "download", "generate", "make",
        "trim", "split", "apply", "animate", "export",
    ] if v in msg.split())

    # Complex if: 2+ complexity signals OR (long message + multiple action verbs)
    if hits >= 2 or (word_count > 20 and has_multiple_verbs >= 2):
        return Intent.COMPLEX_TASK

    # Read-only queries
    query_signals = [
        "what", "how many", "show me", "list", "tell me",
        "describe", "explain", "which", "where is", "is there",
    ]
    if any(msg.startswith(s) for s in query_signals):
        return Intent.SIMPLE_QUERY

    # Default: simple edit (current behavior)
    return Intent.SIMPLE_EDIT


def intent_summary(intent: Intent) -> str:
    """Human-readable description of what the intent means."""
    return {
        Intent.SIMPLE_EDIT: "Direct edit (single action)",
        Intent.SIMPLE_QUERY: "Query (read-only)",
        Intent.COMPLEX_TASK: "Complex task (needs planning)",
        Intent.CONTINUE_TASK: "Continue active plan",
        Intent.CHECK_PROGRESS: "Check plan progress",
        Intent.CANCEL_TASK: "Cancel active plan",
    }.get(intent, "Unknown")


# ── LLM Skill Classifier ─────────────────────────────────────────────────────

def classify_skill_with_llm(
    message: str,
    skills: "list[SkillDef]",
    llm,
) -> "SkillDef | None":
    """Ask LLM to map a user request to the best matching skill.

    Only called when keyword matching fails. Uses a single short LLM call
    (~50 output tokens) — fast and cheap. Returns None if no skill fits well.

    Args:
        message: The user's raw message.
        skills:  List of all loaded SkillDef objects.
        llm:     Pre-built LLM instance (reuse existing, no rebuild cost).

    Returns:
        The best matching SkillDef, or None if no good match found.
    """
    if not skills:
        return None

    from langchain_core.messages import SystemMessage, HumanMessage

    skill_list = "\n".join(
        f"- {s.name}: {s.description[:120].strip()} "
        f"(triggers: {', '.join(s.triggers[:4])})"
        for s in skills
    )

    system = (
        "You are a skill router for a video editing AI. "
        "Given a user request and a list of available skill workflows, "
        "decide which skill BEST matches what the user wants to create. "
        "Be generous — if the request is broadly related to a skill, match it. "
        "Respond with ONLY the skill name exactly as listed, or 'none' if truly no skill fits. "
        "One word only. No explanation."
    )
    user_msg = (
        f"User request: \"{message}\"\n\n"
        f"Available skills:\n{skill_list}"
    )

    try:
        response = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=user_msg),
        ])
        answer = response.content.strip().lower().strip('"\'')
        if answer == "none":
            return None
        # Find exact match
        match = next((s for s in skills if s.name == answer), None)
        if match:
            import logging
            logging.getLogger(__name__).info(
                "[IntentClassifier] LLM matched skill '%s' for: %.60s", answer, message
            )
        return match
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "[IntentClassifier] LLM skill classifier failed: %s", e
        )
        return None
