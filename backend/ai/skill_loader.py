 
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import sys

logger = logging.getLogger(__name__)

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # When bundled by PyInstaller, fall back to the bundled data folder if needed
    SKILLS_DIR = Path(sys._MEIPASS) / "backend" / "ai" / "skills"
    if not SKILLS_DIR.exists():
        SKILLS_DIR = Path(__file__).parent / "skills"
else:
    SKILLS_DIR = Path(__file__).parent / "skills"


# Data classes  

@dataclass
class SkillStep:
    order: int
    name: str          # e.g. "VOICEOVER"
    tool_name: str     # e.g. "generate_tts"
    instruction: str   # full instruction for agent


@dataclass
class SkillDef:
    name: str
    version: str
    triggers: list[str]
    comp_type: str          # "video" | "image" | "pdf"
    agent_type: str         # "video" | "image" | "audio"
    output_dimensions: list[int]
    fps: int
    max_duration_frames: int
    description: str
    rules: list[str]
    steps: list[SkillStep]
    checkpoints: dict[int, str]   # step_order -> checkpoint label
    raw_path: Path = field(default_factory=Path)

    @property
    def trigger_phrase(self) -> str:
        return self.triggers[0] if self.triggers else self.name

    def step_system_prompt(self, step: SkillStep, done_summaries: list[str],
                           goal: str = "") -> str:
        """Build a focused system prompt for one step execution."""
        rules_text = "\n".join(f"  - {r}" for r in self.rules)
        prev_text = ""
        if done_summaries:
            prev_text = "\n\nCompleted steps context:\n" + "\n".join(
                f"  [{i+1}] {s}" for i, s in enumerate(done_summaries)
            )
        goal_text = ""
        if goal:
            goal_text = (
                "USER REQUEST (source of truth for topic, wording, durations, "
                "positions and styling — it overrides the generic step text below):\n"
                f"{goal}\n\n"
            )
        return (
            f"[SKILL: {self.name} v{self.version}]\n"
            f"Step {step.order}/{len(self.steps)}: {step.name}\n"
            f"Primary tool: {step.tool_name}\n\n"
            f"{goal_text}"
            f"Skill Rules (MUST follow):\n{rules_text}\n"
            f"{prev_text}\n\n"
            f"YOUR TASK FOR THIS STEP:\n{step.instruction}\n\n"
            f"Execute this ONE step only, applied to the user request above. "
            f"Use {step.tool_name}() as the main tool, plus any supporting tools this step "
            f"genuinely needs. Do not do work that belongs to other steps.\n"
            f"Only use assetIds / clipIds / compIds returned by a tool or listed in the "
            f"completed-steps context — never invent them. If an asset this step needs "
            f"does not exist yet, create or download it first.\n"
            f"When done, confirm what you did in 1-2 sentences and list every "
            f"assetId / clipId you created so later steps can use them."
        )


#   Parser  

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML-ish frontmatter between --- delimiters. Returns (meta_dict, body)."""
    meta: dict = {}
    body = text

    m = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return meta, body

    fm_text = m.group(1)
    body = m.group(2)

 
    current_key = None
    for line in fm_text.splitlines():
        list_m = re.match(r"^\s{2,}- (.+)$", line)
        if list_m and current_key:
            meta.setdefault(current_key, [])
            if not isinstance(meta[current_key], list):
                meta[current_key] = [meta[current_key]]
            meta[current_key].append(list_m.group(1).strip())
            continue

        kv_m = re.match(r"^(\w+):\s*(.*)", line)
        if kv_m:
            key = kv_m.group(1)
            val = kv_m.group(2).strip().strip('"')
            current_key = key
            # Empty value 
            meta[key] = val if val else []

    # Parse output_dimensions: [1920, 1080]
    if "output_dimensions" in meta and isinstance(meta["output_dimensions"], str):
        nums = re.findall(r"\d+", meta["output_dimensions"])
        meta["output_dimensions"] = [int(n) for n in nums]

    return meta, body


def _parse_section(body: str, heading: str) -> str:
    """Extract content of a ## Heading section."""
    pattern = rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, body, re.DOTALL)
    return m.group(1).strip() if m else ""


def _parse_steps(body: str) -> list[SkillStep]:
    """Parse ## Steps section into SkillStep list."""
    steps_text = _parse_section(body, "Steps")
    steps = []
    # Pattern: "N. NAME | tool_name\n   instruction text"
    pattern = re.compile(
        r"(\d+)\.\s+([A-Z_]+)\s*\|\s*(\w+)\n((?:[ \t]+.+\n?)*)",
        re.MULTILINE,
    )
    for m in pattern.finditer(steps_text):
        order = int(m.group(1))
        name = m.group(2).strip()
        tool_name = m.group(3).strip()
        instruction = re.sub(r"^[ \t]+", "", m.group(4), flags=re.MULTILINE).strip()
        steps.append(SkillStep(order=order, name=name, tool_name=tool_name,
                               instruction=instruction))
    return steps


def _parse_rules(body: str) -> list[str]:
    rules_text = _parse_section(body, "Rules")
    rules = []
    for line in rules_text.splitlines():
        line = line.strip().lstrip("- ").strip()
        if line:
            rules.append(line)
    return rules


def _parse_checkpoints(body: str) -> dict[int, str]:
    """Parse ## Checkpoints: "- 3: LABEL" entries."""
    cp_text = _parse_section(body, "Checkpoints")
    checkpoints: dict[int, str] = {}
    for line in cp_text.splitlines():
        m = re.match(r"-?\s*(\d+):\s+(\w+)", line.strip())
        if m:
            checkpoints[int(m.group(1))] = m.group(2)
    return checkpoints


def _parse_description(body: str) -> str:
    return _parse_section(body, "Description")


def load_skill(path: Path) -> Optional[SkillDef]:
    """Load and parse a single skill .md file. Returns None on error."""
    try:
        text = path.read_text(encoding="utf-8-sig")
        meta, body = _parse_frontmatter(text)

        if not meta.get("name"):
            logger.warning("[SkillLoader] No name in frontmatter: %s", path)
            return None

        triggers = meta.get("triggers", [])
        if isinstance(triggers, str):
            triggers = [triggers]

        dims = meta.get("output_dimensions", [1920, 1080])
        if isinstance(dims, str):
            nums = re.findall(r"\d+", dims)
            dims = [int(n) for n in nums]

        skill = SkillDef(
            name=meta["name"],
            version=str(meta.get("version", "1.0")),
            triggers=triggers,
            comp_type=meta.get("comp_type", "video"),
            agent_type=meta.get("agent_type", "video"),
            output_dimensions=dims,
            fps=int(meta.get("fps", 30)),
            max_duration_frames=int(meta.get("max_duration_frames", 9000)),
            description=_parse_description(body),
            rules=_parse_rules(body),
            steps=_parse_steps(body),
            checkpoints=_parse_checkpoints(body),
            raw_path=path,
        )
        logger.info("[SkillLoader] Loaded skill '%s' (%d steps)", skill.name, len(skill.steps))
        return skill
    except Exception as e:
        logger.error("[SkillLoader] Failed to load %s: %s", path, e)
        return None


#   Registry  

class SkillRegistry:
    """Singleton registry that loads and caches all skills from the skills/ folder."""

    def __init__(self):
        self._skills: dict[str, SkillDef] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        if not SKILLS_DIR.exists():
            logger.warning("[SkillRegistry] skills/ dir not found: %s", SKILLS_DIR)
            return
        for md_file in sorted(SKILLS_DIR.glob("*.md")):
            skill = load_skill(md_file)
            if skill:
                self._skills[skill.name] = skill
        print(f"[SkillRegistry] Loaded {len(self._skills)} skills: "
              f"{list(self._skills.keys())}", flush=True)

    def reload(self) -> int:
        """Force-reload all skill files from disk."""
        self._skills.clear()
        self._loaded = False
        self._ensure_loaded()
        return len(self._skills)

    def match(self, user_prompt: str) -> Optional[SkillDef]:
        """Match user prompt to a skill by trigger keywords. Returns best match or None."""
        self._ensure_loaded()
        prompt_lower = user_prompt.lower()
        best: Optional[SkillDef] = None
        best_score = 0

        for skill in self._skills.values():
            for trigger in skill.triggers:
                if trigger.lower() in prompt_lower:
                    # Longer trigger = more specific = higher score
                    score = len(trigger)
                    if score > best_score:
                        best_score = score
                        best = skill

        if best:
            logger.info("[SkillRegistry] Matched skill '%s' for prompt: %.60s",
                        best.name, user_prompt)
        return best

    def get(self, skill_name: str) -> Optional[SkillDef]:
        self._ensure_loaded()
        return self._skills.get(skill_name)

    def list_skills(self) -> list[dict]:
        self._ensure_loaded()
        return [
            {
                "name": s.name,
                "version": s.version,
                "triggers": s.triggers,
                "comp_type": s.comp_type,
                "steps": len(s.steps),
                "description": s.description[:120],
            }
            for s in self._skills.values()
        ]


# Global singleton
skill_registry = SkillRegistry()
