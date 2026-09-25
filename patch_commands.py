import os

with open('backend/editor_tools/commands.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix AddBrushStrokeCommand
text = text.replace(
    "self.track = self.engine.activeTimeline.tracks[-1]",
    "video_tracks = [t for t in self.engine.activeTimeline.tracks if not getattr(t, 'isAudio', lambda: False)()]\n        self.track = video_tracks[-1] if video_tracks else self.engine.activeTimeline.tracks[0]"
)

with open('backend/editor_tools/commands.py', 'w', encoding='utf-8') as f:
    f.write(text)
