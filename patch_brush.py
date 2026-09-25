import os
with open('backend/editor_tools/commands.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = '''        # Add stroke to the topmost track
        self.track = self.engine.activeTimeline.tracks[-1]
        self.track.addClip(self.clip)'''
replacement = '''        # Add stroke to the topmost track
        self.track = self.engine.activeTimeline.tracks[-1]
        if self.clip not in self.track.clips:
            self.track.addClip(self.clip)'''

text = text.replace(target, replacement)
with open('backend/editor_tools/commands.py', 'w', encoding='utf-8') as f:
    f.write(text)
