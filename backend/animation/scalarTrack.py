from __future__ import annotations
import bisect
import math
from backend.animation.keyframe import Keyframe, Interpolation

 

def _bezierSolveU(p0x: float, p1x: float, p2x: float, p3x: float, targetX: float) -> float:
    """Find u in [0,1] such that bezier_x(u) ≈ targetX."""
    u = (targetX - p0x) / (p3x - p0x) if p3x > p0x else 0.5
    u = max(0.0, min(1.0, u))

    for _ in range(8):
        iu  = 1.0 - u
        bx  = iu*iu*iu*p0x + 3*iu*iu*u*p1x + 3*iu*u*u*p2x + u*u*u*p3x
        dbx = 3*iu*iu*(p1x-p0x) + 6*iu*u*(p2x-p1x) + 3*u*u*(p3x-p2x)
        if abs(dbx) < 1e-7:
            break
        u -= (bx - targetX) / dbx
        u  = max(0.0, min(1.0, u))

    return u


def _bezierEvalY(p0y: float, p1y: float, p2y: float, p3y: float, u: float) -> float:
    iu = 1.0 - u
    return iu*iu*iu*p0y + 3*iu*iu*u*p1y + 3*iu*u*u*p2y + u*u*u*p3y


def _evalBezier(prev: Keyframe, nxt: Keyframe, frame: float) -> float:
    p0x = float(prev.frame)
    p3x = float(nxt.frame)
    p1x = max(p0x, min(p3x, p0x + prev.handleOutFrame))
    p2x = max(p0x, min(p3x, p3x + nxt.handleInFrame))
    p1y = prev.value + prev.handleOutValue
    p2y = nxt.value  + nxt.handleInValue
    u   = _bezierSolveU(p0x, p1x, p2x, p3x, frame)
    return _bezierEvalY(prev.value, p1y, p2y, nxt.value, u)


def _evalEase(prev: Keyframe, nxt: Keyframe, ease: Interpolation, frame: float) -> float:
    p0x = float(prev.frame)
    p3x = float(nxt.frame)
    third = (p3x - p0x) / 3.0

    if ease == Interpolation.EaseIn:
        p1x, p1y = p0x + third, prev.value
        p2x = max(p0x, min(p3x, p3x + nxt.handleInFrame))
        p2y = nxt.value + nxt.handleInValue
    elif ease == Interpolation.EaseOut:
        p1x = max(p0x, min(p3x, p0x + prev.handleOutFrame))
        p1y = prev.value + prev.handleOutValue
        p2x, p2y = p3x - third, nxt.value
    else:  # EaseBoth
        p1x, p1y = p0x + third, prev.value
        p2x, p2y = p3x - third, nxt.value

    p1x = max(p0x, min(p3x, p1x))
    p2x = max(p0x, min(p3x, p2x))
    u = _bezierSolveU(p0x, p1x, p2x, p3x, frame)
    return _bezierEvalY(prev.value, p1y, p2y, nxt.value, u)


#   ScalarTrack  

class ScalarTrack:
    

    def __init__(self) -> None:
        self._frames: list[int] = []   # sorted frame numbers  
        self._keyframes: list[Keyframe] = [] # parallel data

    #   Queries  

    def empty(self) -> bool:
        return len(self._frames) == 0

    def __len__(self) -> int:
        return len(self._frames)

    def hasKeyframe(self, frame: int) -> bool:
        idx = bisect.bisect_left(self._frames, frame)
        return idx < len(self._frames) and self._frames[idx] == frame

    def keyframes(self) -> list[Keyframe]:
        return list(self._keyframes)

    def frameIndex(self) -> list[int]:
        return list(self._frames)

    #   Evaluation  

    def evaluateAt(self, frame: int, defaultValue: float = 0.0) -> float:
        n = len(self._frames)
        if n == 0:
            return defaultValue
        if n == 1:
            return self._keyframes[0].value

        # Binary search  
        nxt = bisect.bisect_right(self._frames, frame)

        if nxt == 0:
            return self._keyframes[0].value
        if nxt == n:
            return self._keyframes[-1].value

        prev_kf = self._keyframes[nxt - 1]
        next_kf = self._keyframes[nxt]

        # Exact hit
        if prev_kf.frame == frame:
            return prev_kf.value

        f = float(frame)
        interp = prev_kf.interp

        if interp == Interpolation.Constant:
            return prev_kf.value

        elif interp == Interpolation.Linear:
            t = (f - prev_kf.frame) / (next_kf.frame - prev_kf.frame)
            return prev_kf.value + t * (next_kf.value - prev_kf.value)

        elif interp == Interpolation.Bezier:
            return _evalBezier(prev_kf, next_kf, f)

        else:  # EaseIn / EaseOut / EaseBoth
            return _evalEase(prev_kf, next_kf, interp, f)

    #   Mutation  

    def insertKeyframe(self, kf: Keyframe) -> None:
        idx = bisect.bisect_left(self._frames, kf.frame)
        if idx < len(self._frames) and self._frames[idx] == kf.frame:
            self._keyframes[idx] = kf   # replace existing
        else:
            self._frames.insert(idx, kf.frame)
            self._keyframes.insert(idx, kf)
        self._recomputeNeighbours(idx)

    def removeKeyframe(self, frame: int) -> bool:
        idx = bisect.bisect_left(self._frames, frame)
        if idx >= len(self._frames) or self._frames[idx] != frame:
            return False
        self._frames.pop(idx)
        self._keyframes.pop(idx)
        if idx > 0:
            self._recomputeAutoHandles(idx - 1)
        if idx < len(self._keyframes):
            self._recomputeAutoHandles(idx)
        return True

    def clear(self) -> None:
        self._frames.clear()
        self._keyframes.clear()

    # Auto-handle recompute  

    def _recomputeNeighbours(self, idx: int) -> None:
        if idx > 0:
            self._recomputeAutoHandles(idx - 1)
        self._recomputeAutoHandles(idx)
        if idx + 1 < len(self._keyframes):
            self._recomputeAutoHandles(idx + 1)

    def _recomputeAutoHandles(self, idx: int) -> None:
        n   = len(self._keyframes)
        if idx >= n:
            return
        kf = self._keyframes[idx]
        isFirst = idx == 0
        isLast  = idx == n - 1

        tangent = 0.0
        if not isFirst and not isLast:
            prev = self._keyframes[idx - 1]
            nxt  = self._keyframes[idx + 1]
            span = float(nxt.frame - prev.frame)
            if span > 0:
                tangent = (nxt.value - prev.value) / span
        elif isFirst and not isLast:
            nxt  = self._keyframes[idx + 1]
            span = float(nxt.frame - kf.frame)
            if span > 0:
                tangent = (nxt.value - kf.value) / span
        elif isLast and not isFirst:
            prev = self._keyframes[idx - 1]
            span = float(kf.frame - prev.frame)
            if span > 0:
                tangent = (kf.value - prev.value) / span

        if isFirst:
            kf.handleInFrame  = -5.0
            kf.handleInValue  =  0.0
        else:
            seg = float(kf.frame - self._keyframes[idx - 1].frame)
            kf.handleInFrame  = -seg / 3.0
            kf.handleInValue  = tangent * kf.handleInFrame

        if isLast:
            kf.handleOutFrame = 5.0
            kf.handleOutValue = 0.0
        else:
            seg = float(self._keyframes[idx + 1].frame - kf.frame)
            kf.handleOutFrame = seg / 3.0
            kf.handleOutValue = tangent * kf.handleOutFrame
