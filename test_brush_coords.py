"""
Headless test: verify that brush stroke pen descriptors carry raw composition-space
coordinates identical to what the native Vector Pen serializer produces.

Portrait 1080x1920 composition:
  - stroke at visual center → composition (540, 960)
  - serialized Pen point must be (540, 960)  ← NOT the renderer-space (960, 540)

Landscape 1920x1080 composition:
  - composition == renderer space → coords unchanged
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.state import engine
from backend.editor_tools.commands import AddBrushStrokeCommand
from backend.routers.render import _get_frame_data
from backend.timeline.tracks.videoTrack import VideoTrack

# ─── PORTRAIT TEST (1080×1920) ──────────────────────────────────────────────
print("=" * 60)
print("TEST 1: Portrait 1080×1920 — center stroke")
print("=" * 60)

engine.newProject("Test")
compId = engine.createComposition("Portrait", 1080, 1920, 30, 300)
engine.project.activeCompId = compId
comp = engine.activeTimeline

# ensure at least one video track
if not comp.tracks:
    comp.tracks.append(VideoTrack("v1"))

# viewport center (960, 540) → viewportToComposition → (540, 960)
CENTER_COMP_X = 540.0
CENTER_COMP_Y = 960.0

cmd = AddBrushStrokeCommand(
    engine,
    [{"x": CENTER_COMP_X, "y": CENTER_COMP_Y}],
    size=10, color=[1.0, 1.0, 1.0, 1.0], opacity=1.0
)
engine.commandStack.execute(cmd)

fd = _get_frame_data(0)

image_clips = [c for c in fd["clips"] if c["type"] == "image"]
pen_clips   = [c for c in fd["clips"] if c["type"] == "pen"]

print(f"Total clips in FD : {len(fd['clips'])}")
print(f"  Image clips      : {len(image_clips)}")
print(f"  Pen clips (brush): {len(pen_clips)}")
assert len(pen_clips) == 1, f"Expected 1 pen clip, got {len(pen_clips)}"

pt = pen_clips[0]["penStyle"]["points"][0]
sw = pen_clips[0]["penStyle"]["strokeWidth"]
print(f"\nSerialized Pen point: ({pt['x']}, {pt['y']})")
print(f"Serialized strokeWidth: {sw}")
print(f"Expected point       : ({CENTER_COMP_X}, {CENTER_COMP_Y})")

assert abs(pt['x'] - CENTER_COMP_X) < 0.01, f"X mismatch: {pt['x']} != {CENTER_COMP_X}"
assert abs(pt['y'] - CENTER_COMP_Y) < 0.01, f"Y mismatch: {pt['y']} != {CENTER_COMP_Y}"
assert abs(sw - 10.0) < 0.01, f"strokeWidth mismatch: {sw} != 10.0"
print("\n✓ Portrait center: PASS — raw composition coords preserved, no double transform")

# ─── LANDSCAPE TEST (1920×1080) ──────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 2: Landscape 1920×1080 — composition == renderer space")
print("=" * 60)

engine.newProject("Test2")
compId2 = engine.createComposition("Landscape", 1920, 1080, 30, 300)
engine.project.activeCompId = compId2
comp2 = engine.activeTimeline

if not comp2.tracks:
    comp2.tracks.append(VideoTrack("v1"))

# center of 1920×1080 landscape
LAND_X, LAND_Y = 960.0, 540.0

cmd2 = AddBrushStrokeCommand(
    engine,
    [{"x": LAND_X, "y": LAND_Y}],
    size=8, color=[0.0, 1.0, 0.0, 1.0], opacity=1.0
)
engine.commandStack.execute(cmd2)

fd2 = _get_frame_data(0)
pen_clips2 = [c for c in fd2["clips"] if c["type"] == "pen"]

assert len(pen_clips2) == 1, f"Expected 1 pen clip, got {len(pen_clips2)}"
pt2 = pen_clips2[0]["penStyle"]["points"][0]
sw2 = pen_clips2[0]["penStyle"]["strokeWidth"]
print(f"\nSerialized Pen point: ({pt2['x']}, {pt2['y']})")
print(f"Expected point       : ({LAND_X}, {LAND_Y})  [identity — comp==renderer]")
assert abs(pt2['x'] - LAND_X) < 0.01, f"X mismatch: {pt2['x']} != {LAND_X}"
assert abs(pt2['y'] - LAND_Y) < 0.01, f"Y mismatch: {pt2['y']} != {LAND_Y}"
assert abs(sw2 - 8.0) < 0.01, f"strokeWidth mismatch: {sw2} != 8.0"
print("✓ Landscape center: PASS — no regression")

# ─── MULTIPLE STROKES ────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 3: Multiple brush strokes")
print("=" * 60)

cmd3 = AddBrushStrokeCommand(
    engine,
    [{"x": 100.0, "y": 200.0}],
    size=5, color=[1.0, 0.0, 0.0, 1.0], opacity=0.8
)
engine.commandStack.execute(cmd3)

fd3 = _get_frame_data(0)
pen_clips3 = [c for c in fd3["clips"] if c["type"] == "pen"]
print(f"Pen clips after 2nd stroke: {len(pen_clips3)}")
assert len(pen_clips3) == 2, f"Expected 2 pen clips, got {len(pen_clips3)}"
print("✓ Multiple strokes: PASS")

# ─── UNDO TEST ────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 4: Undo removes the stroke from FD")
print("=" * 60)

engine.commandStack.undo()
fd4 = _get_frame_data(0)
pen_clips4 = [c for c in fd4["clips"] if c["type"] == "pen"]
print(f"Pen clips after undo: {len(pen_clips4)}")
assert len(pen_clips4) == 1, f"Expected 1 pen clip after undo, got {len(pen_clips4)}"
print("✓ Undo: PASS — stroke disappears from FD")

# ─── REDO TEST ────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 5: Redo restores the stroke")
print("=" * 60)

engine.commandStack.redo()
fd5 = _get_frame_data(0)
pen_clips5 = [c for c in fd5["clips"] if c["type"] == "pen"]
print(f"Pen clips after redo: {len(pen_clips5)}")
assert len(pen_clips5) == 2, f"Expected 2 pen clips after redo, got {len(pen_clips5)}"
print("✓ Redo: PASS — stroke reappears in FD")

# ─── VERIFY NO LETTERBOX in the FD ───────────────────────────────────────────
print()
print("=" * 60)
print("TEST 6: Verify NO letterbox transform applied to Brush Pen points")
print("=" * 60)

# For portrait 1080×1920: if letterbox were applied, (540,960) would become ~(960,540)
# If raw, it remains (540,960)
engine.newProject("Test6")
compId6 = engine.createComposition("PortraitCheck", 1080, 1920, 30, 300)
engine.project.activeCompId = compId6
comp6 = engine.activeTimeline
if not comp6.tracks:
    comp6.tracks.append(VideoTrack("v1"))

cmd6 = AddBrushStrokeCommand(
    engine,
    [{"x": 540.0, "y": 960.0}],
    size=10, color=[1.0, 1.0, 1.0, 1.0], opacity=1.0
)
engine.commandStack.execute(cmd6)

fd6 = _get_frame_data(0)
pen6 = [c for c in fd6["clips"] if c["type"] == "pen"]
pt6 = pen6[0]["penStyle"]["points"][0]

letterbox_applied = abs(pt6['x'] - 960.0) < 5 and abs(pt6['y'] - 540.0) < 5
raw_preserved     = abs(pt6['x'] - 540.0) < 5 and abs(pt6['y'] - 960.0) < 5

print(f"Point in FD: ({pt6['x']:.1f}, {pt6['y']:.1f})")
print(f"Letterbox transform applied? {letterbox_applied}  (MUST BE False)")
print(f"Raw composition coords?      {raw_preserved}      (MUST BE True)")
assert raw_preserved,     "FAIL: raw composition coords not preserved!"
assert not letterbox_applied, "FAIL: letterbox was applied — double transform detected!"
print("✓ No double transform: PASS")

print()
print("=" * 60)
print("ALL TESTS PASSED ✓")
print("=" * 60)
print("""
Complete coordinate chain (portrait 1080×1920):
  mouse client    →  viewport (960, 540)   [DOM pixels]
  getPt()         →  logical  (960, 540)   [1920×1080 canvas space via rect scale]
  viewportToComp  →  comp     (540, 960)   [composition space, with letterbox inverse]
  brush_strokes   →  stored   (540, 960)   [ImageClip]
  render.py FD    →  pen pt   (540, 960)   [RAW — no transform]
  C++ compositor  →  canvas   (960, 540)   [letterbox applied once by GPU camera]
  final output    →  visual center ✓
""")
