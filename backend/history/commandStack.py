from __future__ import annotations
from abc import ABC, abstractmethod
from collections import deque


class Command(ABC):
  
    @abstractmethod
    def execute(self) -> None:
         
        ...

    @abstractmethod
    def undo(self) -> None:
         ...

    @property
    def description(self) -> str:
        
        return self.__class__.__name__


class CommandStack:
    

    def __init__(self, maxHistory: int = 100) -> None:
        self._undoStack: deque[Command] = deque(maxlen=maxHistory)
        self._redoStack: deque[Command] = deque()
        self._isDirty   = False

    #   Core operations  

    def execute(self, cmd: Command) -> None:
        """Run a command and push it onto the undo stack."""
        cmd.execute()
        self._undoStack.append(cmd)
        self._redoStack.clear()    
        self._isDirty = True

    def undo(self) -> str | None:
        """Undo the last command. Returns its description, or None if empty."""
        if not self._undoStack:
            return None
        cmd = self._undoStack.pop()
        cmd.undo()
        self._redoStack.append(cmd)
        self._isDirty = True
        return cmd.description

    def redo(self) -> str | None:
        """Redo the last undone command. Returns its description, or None."""
        if not self._redoStack:
            return None
        cmd = self._redoStack.pop()
        cmd.execute()
        self._undoStack.append(cmd)
        self._isDirty = True
        return cmd.description

    # State queries  

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
        return (
            f"CommandStack("
            f"undo={len(self._undoStack)}, "
            f"redo={len(self._redoStack)})"
        )


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
    def __init__(self, clip, oldStart: int, newStart: int) -> None:
        self._clip     = clip
        self._oldStart = oldStart
        self._newStart = newStart

    def execute(self) -> None:
        self._clip.startFrame = self._newStart

    def undo(self) -> None:
        self._clip.startFrame = self._oldStart

    @property
    def description(self) -> str:
        return f"Move clip {self._oldStart} → {self._newStart}"


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
        self._track    = track
        self._index    = timeline.tracks.index(track)

    def execute(self) -> None:
        self._timeline.removeTrack(self._track.trackId)

    def undo(self) -> None:
        self._timeline.tracks.insert(self._index, self._track)

    @property
    def description(self) -> str:
        return f"Remove track '{self._track.name}'"
