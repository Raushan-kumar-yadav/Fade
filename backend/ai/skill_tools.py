
from __future__ import annotations
from langchain_core.tools import tool


@tool
def list_skills() -> str:
    """List all skill workflows currently loaded from the skills/ directory.
    Skills are .md files in backend/ai/skills/. Any new .md file added there
    is automatically indexed and available. Call this to see what skills
    are available before answering the user's question about capabilities.
    Returns name, description, step count, and trigger phrases for each skill.
    """
    try:
        from backend.ai.skill_loader import skill_registry
        skills = [skill_registry.get(s["name"]) for s in skill_registry.list_skills()]
        skills = [s for s in skills if s]
    except Exception as e:
        return f"Error loading skills: {e}"

    if not skills:
        return (
            "No skills currently loaded.\n"
            "Skills are .md files placed in backend/ai/skills/.\n"
            "The user can import new skills via Settings > Skills tab."
        )

    lines = [f"{len(skills)} skill(s) loaded from disk:\n"]
    for skill in skills:
        step_names = [s.name for s in skill.steps]
        lines += [
            f"Name: {skill.name}",
            f"Version: v{skill.version}",
            f"Description: {skill.description[:300].strip()}",
            f"Triggers: {', '.join(skill.triggers)}",
            f"Steps ({len(skill.steps)}): {' → '.join(step_names)}",
            f"Checkpoints: {skill.checkpoints}",
            "",
        ]
    return "\n".join(lines)


@tool
def read_skill(skill_name: str) -> str:
    """Read the full content of a skill .md file by skill name.
    Returns the raw markdown including frontmatter, description, rules, steps,
    and checkpoints. Use this when the user asks for details about a specific skill,
    or when you need to understand what a skill does before running it.

    Args:
        skill_name: The name of the skill (e.g. 'educational_video', 'product_demo')
    """
    try:
        from backend.ai.skill_loader import skill_registry
        skill = skill_registry.get(skill_name)
    except Exception as e:
        return f"Error reading skill registry: {e}"

    if not skill:
        try:
            from backend.ai.skill_loader import skill_registry
            available = [s["name"] for s in skill_registry.list_skills()]
        except Exception:
            available = []
        return (
            f"Skill '{skill_name}' not found.\n"
            f"Available skills: {available}\n"
            "Try list_skills() to see all loaded skills."
        )

    # Read raw .md content from disk
    try:
        raw_md = skill.raw_path.read_text(encoding="utf-8-sig")
    except Exception as e:
        raw_md = f"[Could not read file: {e}]"

    return (
        f"=== Skill: {skill.name} (v{skill.version}) ===\n"
        f"File: {skill.raw_path}\n\n"
        f"{raw_md}"
    )


@tool
def reload_skills() -> str:
    """Force-reload all skill .md files from the backend/ai/skills/ directory.
    Use this after the user imports a new skill file via Settings > Skills,
    or after manually placing a .md file in the skills folder.
    Returns the count of skills now loaded.
    """
    try:
        from backend.ai.skill_loader import skill_registry
        count = skill_registry.reload()
        names = [s["name"] for s in skill_registry.list_skills()]
        return (
            f"Skills reloaded from disk. {count} skill(s) now active:\n"
            + "\n".join(f"  - {n}" for n in names)
        )
    except Exception as e:
        return f"Error reloading skills: {e}"


SKILL_TOOLS = [list_skills, read_skill, reload_skills]
