from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum


class Interpolation(IntEnum):
    Constant = 0
    Linear   = 1
    Bezier   = 2
    EaseIn   = 3
    EaseOut  = 4
    EaseBoth = 5


@dataclass
class Keyframe:
   
    frame: int
    value: float
    interp: Interpolation = Interpolation.Bezier
    handleInFrame: float = -5.0
    handleInValue: float =  0.0
    handleOutFrame: float =  5.0
    handleOutValue: float =  0.0


# helpers 

def makeConstantKeyframe(frame: int, value: float) -> Keyframe:
    return Keyframe(frame, value, Interpolation.Constant)

def makeLinearKeyframe(frame: int, value: float) -> Keyframe:
    return Keyframe(frame, value, Interpolation.Linear)

def makeBezierKeyframe(
    frame: int, value: float,
    handleInFrame: float = -5.0, handleInValue: float = 0.0,
    handleOutFrame: float = 5.0, handleOutValue: float = 0.0,
) -> Keyframe:
    return Keyframe(frame, value, Interpolation.Bezier,
                    handleInFrame, handleInValue, handleOutFrame, handleOutValue)

def makeEaseKeyframe(
    frame: int, value: float,
    ease: Interpolation = Interpolation.EaseBoth,
) -> Keyframe:
    return Keyframe(frame, value, ease)
