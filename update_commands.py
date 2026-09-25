import re
with open('backend/editor_tools/commands.py', 'r') as f:
    content = f.read()

pattern = re.compile(r'    def execute\(self\) -> None:\n        from backend\.timeline\.clips\.imageClip import ImageClip, BrushStroke\n        import uuid\n\n        if not self\.engine\.activeTimeline or not self\.engine\.activeTimeline\.tracks:\n            return\n\n        # Reuse previously created objects on redo\n        if self\._stroke is not None:.*?self\.clip    = img_clip   # legacy compat', re.DOTALL)

replacement = """    def execute(self) -> None:
        from backend.timeline.clips.imageClip import ImageClip, BrushStroke
        import uuid

        if not self.engine.activeTimeline or not self.engine.activeTimeline.tracks:
            return

        if self._stroke is not None:
            if self._created_clip and self._clip not in self._track.clips:
                self._track.addClip(self._clip)
            self._clip.brush_strokes.append(self._stroke)
            self.clip = self._clip
            return

        clip, track = self._find_selected_brushable_clip()
        
        points_to_save = list(self.points)
        if clip and getattr(clip, "clipType", getattr(clip, "CLIP_TYPE", "")) != "image":
            from backend.editor_tools.transform_utils import comp_to_local
            points_to_save = [comp_to_local(p, clip.transform) for p in self.points]

        if clip is None:
            vtracks = self._video_tracks(self.engine.activeTimeline)
            track = vtracks[-1] if vtracks else self.engine.activeTimeline.tracks[0]
            clip = ImageClip(
                clipId     = str(uuid.uuid4()),
                startFrame = 0,
                duration   = 150,
                assetId    = "",
                filepath   = "",
                color      = (0, 0, 0, 0),
            )
            track.addClip(clip)
            self._created_clip = True

        stroke = BrushStroke(
            points  = points_to_save,
            size    = self.size,
            color   = list(self.color),
            opacity = self.opacity,
        )
        clip.brush_strokes.append(stroke)

        self._stroke = stroke
        self._clip   = clip
        self._track  = track
        self.clip    = clip"""

content, n = pattern.subn(replacement, content)
print(f'Replaced {n} occurrences')
with open('backend/editor_tools/commands.py', 'w') as f:
    f.write(content)
