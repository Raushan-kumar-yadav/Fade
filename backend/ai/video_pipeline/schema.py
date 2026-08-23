"""
backend/ai/video_pipeline/schema.py
Pydantic models for the AI Scene Plan JSON schema.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class EffectConfig(BaseModel):
    name: str = Field(description="Effect name: 'blur', 'brightness', 'contrast', 'vignette'")
    params: dict = Field(default_factory=dict, description="Effect-specific parameters")
    fromFrame: int = Field(0, description="Relative frame within scene where effect starts")
    toFrame: int = Field(30, description="Relative frame within scene where effect ends")


class BrollConfig(BaseModel):
    type: Literal["video", "image", "none"] = Field(
        description="Type of b-roll: 'video' (yt-dlp search), 'image' (Gemini generation), 'none'"
    )
    searchQuery: str = Field(
        default="",
        description="For type=video: short cinematic YouTube search query (5-8 words)"
    )
    generatePrompt: str = Field(
        default="",
        description="For type=image: detailed Imagen-style prompt with rich descriptors"
    )
    fromFrame: int = Field(0, description="Absolute timeline frame where b-roll starts")
    toFrame: int = Field(150, description="Absolute timeline frame where b-roll ends")
    track: int = Field(0, description="Timeline track index for b-roll (always 0)")
    effects: list[EffectConfig] = Field(
        default_factory=list,
        description="Optional effects applied to this b-roll clip"
    )


class TitleConfig(BaseModel):
    textContent: str = Field(description="Main headline text to display")
    fontSize: float = Field(52.0, description="Font size in points")
    dropShadow: bool = Field(True, description="Whether to apply drop shadow")
    bold: bool = Field(True)
    color: str = Field("#FFFFFF", description="Text color as hex")
    backgroundEnabled: bool = Field(True)
    backgroundColor: str = Field("#00000088", description="Background fill as hex with alpha")
    fromFrame: int = Field(0, description="Absolute timeline frame where title starts")
    toFrame: int = Field(150, description="Absolute timeline frame where title ends")
    track: int = Field(1, description="Timeline track index for title (always 1)")


class LowerThirdConfig(BaseModel):
    textContent: str = Field(description="Short source / category label, e.g. 'TECHNOLOGY'")
    fontSize: float = Field(28.0)
    color: str = Field("#FFDD00")
    backgroundEnabled: bool = Field(True)
    backgroundColor: str = Field("#000000CC")
    fromFrame: int = 0
    toFrame: int = 90
    track: int = Field(2, description="Timeline track index for lower-third (always 2)")


class Scene(BaseModel):
    id: int = Field(description="1-based scene index")
    headline: str = Field(description="Short news headline for this scene")
    summary: str = Field(description="One-sentence news summary")
    fromFrame: int = Field(description="Absolute timeline frame where scene starts")
    toFrame: int = Field(description="Absolute timeline frame where scene ends")
    broll: BrollConfig
    title: TitleConfig
    lowerThird: LowerThirdConfig | None = None


class ScenePlan(BaseModel):
    query: str = Field(description="The original user query")
    totalScenes: int
    fps: float = 30.0
    totalFrames: int
    scenes: list[Scene]
