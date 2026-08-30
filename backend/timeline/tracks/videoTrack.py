from __future__ import annotations
from backend.timeline.tracks.baseTrack import BaseTrack
from backend.timeline.clips.baseClip import BaseClip


class VideoTrack(BaseTrack):
     

    TRACK_TYPE = "video"

    def __init__(self, name: str = "Video Track") -> None:
        super().__init__(name)
        self.opacity: float = 1.0
        self.transitions: list = []   # list[Transition]

    #   Transition helpers  

    def getTransitionAt(self, frame: int):
        """
        If `frame` falls inside any transition zone return
        (Transition, progress, clipA, clipB).
        Otherwise return None.
        """
        for tr in self.transitions:
            # Resolve clips by id
            clipA = next((c for c in self.clips if c.clipId == tr.clipA_id), None)
            clipB = next((c for c in self.clips if c.clipId == tr.clipB_id), None)
            if clipA is None or clipB is None:
                continue
            start = tr.transitionStart(clipA.endFrame)
            end   = tr.transitionEnd(clipA.endFrame)
            if start <= frame < end:
                prog = tr.progress(frame, clipA.endFrame)
                return (tr, prog, clipA, clipB)
        return None

    def addTransition(self, transition) -> None:
        """Add or replace the transition between the same clip pair."""
        self.transitions = [
            t for t in self.transitions
            if not (t.clipA_id == transition.clipA_id and
                    t.clipB_id == transition.clipB_id)
        ]
        self.transitions.append(transition)

    def removeTransition(self, transId: str) -> None:
        self.transitions = [t for t in self.transitions if t.transId != transId]

    # Legacy render  

    def render(self, canvas, frame: int) -> None:
        if self.muted:
            return
        clip = self.clipAt(frame)
        if clip is None:
            return
        clip.render(canvas, frame)
        for effect in clip.effects:
            if effect.enabled:
                effect.apply(canvas, frame)

    #   Serialisation  

    def toDict(self) -> dict:
        d = self._baseDict()
        d["type"]        = self.TRACK_TYPE
        d["opacity"]     = self.opacity
        d["transitions"] = [t.toDict() for t in self.transitions]
        return d

    @classmethod
    def fromDict(cls, data: dict) -> "VideoTrack":
        from backend.timeline.clips.videoClip  import VideoClip
        from backend.timeline.clips.imageClip   import ImageClip
        from backend.timeline.clips.textClip    import TextClip
        from backend.timeline.clips.shapeClip   import ShapeClip
        from backend.timeline.clips.penClip     import PenClip
        from backend.timeline.clips.svgClip     import SvgClip
        from backend.timeline.clips.compClip    import CompClip
        from backend.timeline.clips.webComp     import WebCompClip
        from backend.timeline.transitions.transition import Transition

        _CLIP_REGISTRY = {
            "video":   VideoClip,
            "image":   ImageClip,
            "text":    TextClip,
            "shape":   ShapeClip,
            "pen":     PenClip,
            "svg":     SvgClip,
            "comp":    CompClip,
            "webcomp": WebCompClip,
        }

        t = cls(name=data["name"])
        t._applyBaseDict(data)
        t.opacity = data.get("opacity", 1.0)
        for clipData in data.get("clips", []):
            # Clips serialized with "type" (VideoClip, ImageClip…) or "clipType" (TextClip, ShapeClip…)
            clip_type = clipData.get("type") or clipData.get("clipType") or "video"
            clip_cls  = _CLIP_REGISTRY.get(clip_type, VideoClip)
            try:
                t.clips.append(clip_cls.fromDict(clipData))
            except Exception as e:
                print(f"[VideoTrack] WARNING: could not load clip type={clip_type!r}: {e}", flush=True)
        for td in data.get("transitions", []):
            t.transitions.append(Transition.fromDict(td))
        return t
