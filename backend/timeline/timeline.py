from __future__ import annotations
import uuid
from backend.timeline.tracks.baseTrack import BaseTrack


class Timeline:
    
    def __init__(self, name: str = "Sequence 01") -> None:
        self.timelineId = str(uuid.uuid4())
        self.name = name
        self.tracks: list[BaseTrack] = []
        self.playheadFrame = 0
        # Timeline-level transitions  
        self.transitions: list = []   # list[Transition]

    #   Clip lookup 

    def findClip(self, clipId: str):
        """Return (clip, track) or (None, None)."""
        for track in self.tracks:
            for clip in track.clips:
                if clip.clipId == clipId:
                    return clip, track
        return None, None

    #   Transition management  

    def addTransition(self, transition) -> None:
        """Add or replace the transition for the same clip pair."""
        self.transitions = [
            t for t in self.transitions
            if not (t.clipA_id == transition.clipA_id and
                    t.clipB_id == transition.clipB_id)
        ]
        self.transitions.append(transition)

    def removeTransition(self, transId: str) -> None:
        self.transitions = [t for t in self.transitions if t.transId != transId]

    def getTransitionAt(self, frame: int):
         
        for tr in self.transitions:
            clipA, _ = self.findClip(tr.clipA_id)
            clipB, _ = self.findClip(tr.clipB_id)
            if clipA is None or clipB is None:
                continue
            start = tr.transitionStart(clipA.endFrame)
            end   = tr.transitionEnd(clipA.endFrame)
            if start <= frame < end:
                prog = tr.progress(frame, clipA.endFrame)
                return (tr, prog, clipA, clipB)
        return None

    def getTransitionsForTrack(self, trackId: str) -> list:
        """Return transitions where clipA *or* clipB belongs to the given track."""
        result = []
        for tr in self.transitions:
            _, trackA = self.findClip(tr.clipA_id)
            _, trackB = self.findClip(tr.clipB_id)
            if (trackA and getattr(trackA, 'trackId', None) == trackId) or \
               (trackB and getattr(trackB, 'trackId', None) == trackId):
                result.append(tr)
        return result

    # Track management

    def addTrack(self, track: BaseTrack) -> None:
        self.tracks.append(track)

    def removeTrack(self, trackId: str) -> None:
        self.tracks = [t for t in self.tracks if t.trackId != trackId]

    def getTrack(self, trackId: str) -> BaseTrack | None:
        return next((t for t in self.tracks if t.trackId == trackId), None)

    def moveTrack(self, trackId: str, newIndex: int) -> None:
        track = self.getTrack(trackId)
        if track is None:
            return
        self.tracks.remove(track)
        self.tracks.insert(newIndex, track)

    # Rendering  

    def render(self, canvas, frame: int) -> None:
        for track in reversed(self.tracks):
            if not track.muted:
                track.render(canvas, frame)

    # Serialization

    def toDict(self) -> dict:
        return {
            "timelineId": self.timelineId,
            "name": self.name,
            "playheadFrame": self.playheadFrame,
            "tracks": [t.toDict() for t in self.tracks],
            "transitions": [t.toDict() for t in self.transitions],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "Timeline":
        from backend.timeline.tracks.videoTrack import VideoTrack
        from backend.timeline.tracks.audioTrack import AudioTrack
        from backend.timeline.transitions.transition import Transition

        _TRACK_REGISTRY = {
            "video": VideoTrack,
            "audio": AudioTrack,
        }

        t = cls(name=data["name"])
        t.timelineId = data["timelineId"]
        t.playheadFrame = data.get("playheadFrame", 0)

        for trackData in data.get("tracks", []):
            trackType = trackData.get("type", "video")
            trackCls  = _TRACK_REGISTRY.get(trackType)
            if trackCls:
                t.tracks.append(trackCls.fromDict(trackData))

        # Load timeline-level transitions
        for td in data.get("transitions", []):
            t.transitions.append(Transition.fromDict(td))

        # Back-compat 
        for track in t.tracks:
            for tr in getattr(track, 'transitions', []):
                if not any(x.transId == tr.transId for x in t.transitions):
                    t.transitions.append(tr)

        return t

    def __repr__(self) -> str:
        return (
            f"Timeline({self.name!r}, "
            f"{len(self.tracks)} tracks, "
            f"frame={self.playheadFrame})"
        )
