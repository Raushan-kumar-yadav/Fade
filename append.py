import sys

code = """
class TransformClipCommand(Command):
    def __init__(self, clip_id: str, before: dict, after: dict):
        self.clip_id = clip_id
        self.before = before
        self.after = after
    
    @property
    def undoDescription(self) -> str:
        return "Undo Transform"
        
    @property
    def redoDescription(self) -> str:
        return "Redo Transform"
        
    def _apply(self, params: dict):
        from backend.state import engine
        tl = engine.activeTimeline
        if not tl: return
        clip = None
        for track in tl.tracks:
            for c in track.clips:
                if getattr(c, "clipId", getattr(c, "id", "")) == self.clip_id:
                    clip = c
                    break
            if clip: break
        if not clip: return
        
        for k, v in params.items():
            clip.applyParam(k, float(v))
            if hasattr(clip, "_lastFrame"):
                clip._lastFrame = -1
                
        from backend.events import notify
        notify("timeline")
        notify("render")
        
    def do(self) -> None:
        self._apply(self.after)
        
    def undo(self) -> None:
        self._apply(self.before)
"""

with open('backend/editor_tools/commands.py', 'a') as f:
    f.write(code)
