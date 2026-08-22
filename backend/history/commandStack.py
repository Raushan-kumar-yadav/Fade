from __future__ import annotations
from abc import ABC, abstractmethod
from collections import deque


class Command(ABC):
    @abstractmethod
    def execute(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...

    @property
    def description(self) -> str:
        return self.__class__.__name__


class CommandStack:
    def __init__(self, maxHistory: int = 100) -> None:
        self._undoStack: deque[Command] = deque(maxlen=maxHistory)
        self._redoStack: deque[Command] = deque()

    def execute(self, cmd: Command) -> None:
        cmd.execute()
        self._undoStack.append(cmd)
        self._redoStack.clear()

    def undo(self) -> str | None:
        if not self._undoStack:
            return None
        cmd = self._undoStack.pop()
        cmd.undo()
        self._redoStack.append(cmd)
        return cmd.description

    def redo(self) -> str | None:
        if not self._redoStack:
            return None
        cmd = self._redoStack.pop()
        cmd.execute()
        self._undoStack.append(cmd)
        return cmd.description

    @property
    def canUndo(self) -> bool:
        return len(self._undoStack) > 0

    @property
    def canRedo(self) -> bool:
        return len(self._redoStack) > 0

    @property
    def undoDescription(self) -> str | None:
        return self._undoStack[-1].description if self._undoStack else None

    @property
    def redoDescription(self) -> str | None:
        return self._redoStack[-1].description if self._redoStack else None

    def clear(self) -> None:
        self._undoStack.clear()
        self._redoStack.clear()

    def __repr__(self) -> str:
        return f"CommandStack(undo={len(self._undoStack)}, redo={len(self._redoStack)})"


# Concrete commands  

class AddClipCommand(Command):
    def __init__(self, track, clip) -> None:
        self._track = track
        self._clip  = clip

    def execute(self) -> None:
        self._track.addClip(self._clip)

    def undo(self) -> None:
        self._track.removeClip(self._clip.clipId)

    @property
    def description(self) -> str:
        return f"Add clip '{self._clip.clipId}'"


class RemoveClipCommand(Command):
    def __init__(self, track, clip) -> None:
        self._track = track
        self._clip  = clip

    def execute(self) -> None:
        self._track.removeClip(self._clip.clipId)

    def undo(self) -> None:
        self._track.addClip(self._clip)

    @property
    def description(self) -> str:
        return f"Remove clip '{self._clip.clipId}'"


class MoveClipCommand(Command):
    """Move clip to a new startFrame, optionally across tracks."""

    def __init__(self, clip, oldTrack, newTrack, oldStart: int, newStart: int) -> None:
        self._clip     = clip
        self._oldTrack = oldTrack
        self._newTrack = newTrack
        self._oldStart = oldStart
        self._newStart = newStart

    def execute(self) -> None:
        self._oldTrack.removeClip(self._clip.clipId)
        self._clip.startFrame = self._newStart
        self._newTrack.addClip(self._clip)

    def undo(self) -> None:
        self._newTrack.removeClip(self._clip.clipId)
        self._clip.startFrame = self._oldStart
        self._oldTrack.addClip(self._clip)

    @property
    def description(self) -> str:
        return f"Move clip {self._oldStart} -> {self._newStart}"


class TrimClipCommand(Command):
    """Trim the left or right edge of a clip by frameDelta frames."""

    def __init__(self, clip, side: str, frameDelta: int) -> None:
        self._clip       = clip
        self._side       = side          # 'left' or 'right'
        self._frameDelta = frameDelta
        self._oldStart   = clip.startFrame
        self._oldDuration = clip.duration

    def execute(self) -> None:
        clip = self._clip
        if self._side == 'left':
            newStart = max(0, clip.startFrame + self._frameDelta)
            newDur   = clip.duration - (newStart - clip.startFrame)
            if newDur >= 1:
                clip.startFrame = newStart
                clip.duration   = newDur
        else:
            clip.duration = max(1, clip.duration + self._frameDelta)

    def undo(self) -> None:
        self._clip.startFrame = self._oldStart
        self._clip.duration   = self._oldDuration

    @property
    def description(self) -> str:
        return f"Trim {self._side} edge by {self._frameDelta}f"


class SplitClipCommand(Command):
    """Split a clip at a global timeline frame into two clips."""

    def __init__(self, track, clip, globalFrame: int,
                 scheduler=None, asset=None, fps: float = 30.0) -> None:
        self._track = track
        self._original = clip
        self._globalFrame  = globalFrame
        self._scheduler = scheduler
        self._asset = asset
        self._fps = fps
        self._rightClip    = None
        self._origDuration = clip.duration

    def execute(self) -> None:
        from backend.timeline.clips.videoClip import VideoClip

        clip = self._original
        splitLocal = self._globalFrame - clip.startFrame

        if splitLocal <= 0 or splitLocal >= clip.duration:
            raise ValueError(f"Split point {self._globalFrame} is outside clip bounds "
                             f"[{clip.startFrame}, {clip.startFrame + clip.duration})")

        clip.duration = splitLocal

        right = VideoClip(
            startFrame = self._globalFrame,
            duration = self._origDuration - splitLocal,
            assetId = clip.assetId,
            color = getattr(clip, 'color', (74, 144, 226, 255)),
        )
        self._rightClip = right
        self._track.addClip(right)

        if self._scheduler and self._asset:
            right.setScheduler(self._scheduler, self._fps)
            self._scheduler.registerClip(right.clipId, self._asset)

    def undo(self) -> None:
        if self._rightClip:
            if self._scheduler:
                self._scheduler.unregisterClip(self._rightClip.clipId)
            self._track.removeClip(self._rightClip.clipId)
            self._rightClip = None
        self._original.duration = self._origDuration

    @property
    def description(self) -> str:
        return f"Split clip at frame {self._globalFrame}"


class AddTrackCommand(Command):
    def __init__(self, timeline, track) -> None:
        self._timeline = timeline
        self._track    = track

    def execute(self) -> None:
        self._timeline.addTrack(self._track)

    def undo(self) -> None:
        self._timeline.removeTrack(self._track.trackId)

    @property
    def description(self) -> str:
        return f"Add track '{self._track.name}'"


class RemoveTrackCommand(Command):
    def __init__(self, timeline, track) -> None:
        self._timeline = timeline
        self._track = track
        self._index = timeline.tracks.index(track)

    def execute(self) -> None:
        self._timeline.removeTrack(self._track.trackId)

    def undo(self) -> None:
        self._timeline.tracks.insert(self._index, self._track)

    @property
    def description(self) -> str:
        return f"Remove track '{self._track.name}'"


class SetParamCommand(Command):
    """Undo/redo command stack"""

    def __init__(self, clip, key: str, old_val: float, new_val: float, frame: int = -1) -> None:
        self._clip = clip
        self._key = key
        self._old_val = old_val
        self._new_val = new_val
        self._frame = frame

    def _apply(self, value: float) -> None:
        if hasattr(self._clip, '_anim_params') and self._key in self._clip._anim_params:
            ap = self._clip._anim_params[self._key]
            if self._frame >= 0:
                ap.addKeyframe(self._frame, value)
            else:
                ap.setBaseValue(value)
        else:
            self._clip.applyParam(self._key, value)

    def execute(self) -> None:
        self._apply(self._new_val)

    def undo(self) -> None:
        self._apply(self._old_val)

    @property
    def description(self) -> str:
        return f"Set {self._key} = {self._new_val:.3f}"


class AddKeyframeCommand(Command):
    def __init__(self, ap, frame: int, value: float) -> None:
        self._ap    = ap
        self._frame = frame
        self._value = value
        self._had   = ap.hasKeyframe(frame)
        self._old   = ap.track.evaluateAt(frame, ap.baseValue) if self._had else None

    def execute(self) -> None:
        self._ap.addKeyframe(self._frame, self._value)

    def undo(self) -> None:
        if self._had and self._old is not None:
            self._ap.addKeyframe(self._frame, self._old)
        else:
            self._ap.removeKeyframe(self._frame)

    @property
    def description(self) -> str:
        return f"Add keyframe at {self._frame}"


class DeleteKeyframeCommand(Command):
    def __init__(self, ap, frame: int) -> None:
        self._ap    = ap
        self._frame = frame
        self._value = ap.track.evaluateAt(frame, ap.baseValue) if ap.hasKeyframe(frame) else None

    def execute(self) -> None:
        self._ap.removeKeyframe(self._frame)

    def undo(self) -> None:
        if self._value is not None:
            self._ap.addKeyframe(self._frame, self._value)

    @property
    def description(self) -> str:
        return f"Delete keyframe at {self._frame}"
