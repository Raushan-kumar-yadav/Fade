"""Minimal headless coord chain test - ASCII only"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.state import engine
from backend.editor_tools.commands import AddBrushStrokeCommand
from backend.routers.render import _get_frame_data
from backend.timeline.tracks.videoTrack import VideoTrack

PASS = "PASS"
FAIL = "FAIL"

def run_test(name, comp_w, comp_h, stroke_x, stroke_y, stroke_size):
    engine.newProject(name)
    cid = engine.createComposition(name, comp_w, comp_h, 30, 300)
    engine.project.activeCompId = cid
    comp = engine.activeTimeline
    if not comp.tracks:
        comp.tracks.append(VideoTrack("v1"))
    
    cmd = AddBrushStrokeCommand(engine, [{"x": stroke_x, "y": stroke_y}], stroke_size, [1,1,1,1], 1.0)
    cmd.execute()

    fd = _get_frame_data(0)
    pens = [c for c in fd["clips"] if c["type"] == "pen"]
    
    assert len(pens) >= 1, f"No pen clips in FD! clips={[c['type'] for c in fd['clips']]}"
    pt = pens[0]["penStyle"]["points"][0]
    sw = pens[0]["penStyle"]["strokeWidth"]
    
    x_ok = abs(pt["x"] - stroke_x) < 0.01
    y_ok = abs(pt["y"] - stroke_y) < 0.01
    w_ok = abs(sw - stroke_size) < 0.01
    ok = x_ok and y_ok and w_ok
    
    print(f"[{name}] comp={comp_w}x{comp_h} stroke_in=({stroke_x},{stroke_y}) size={stroke_size}")
    print(f"  serialized point: ({pt['x']}, {pt['y']})  strokeWidth: {sw}")
    print(f"  x_ok={x_ok}  y_ok={y_ok}  w_ok={w_ok}  ==> {PASS if ok else FAIL}")
    
    # check no letterbox applied for portrait
    if comp_h > comp_w:
        scale = min(1920.0/comp_w, 1080.0/comp_h)
        off_x = (1920.0 - comp_w*scale)/2.0
        letterboxed_x = stroke_x * scale + off_x
        letterboxed_y = stroke_y * scale
        double_xform = abs(pt["x"] - letterboxed_x) < 1.0 and abs(pt["y"] - letterboxed_y) < 1.0
        print(f"  letterbox would give ({letterboxed_x:.1f},{letterboxed_y:.1f}); double_xform={double_xform} (MUST be False)")
        assert not double_xform, "FAIL: double letterbox transform detected!"
    
    print()
    return ok

all_ok = True

# Portrait 1080x1920
all_ok &= run_test("Portrait-Center", 1080, 1920, 540.0, 960.0, 10)
all_ok &= run_test("Portrait-TopLeft", 1080, 1920, 100.0, 100.0, 5)
all_ok &= run_test("Portrait-BottomRight", 1080, 1920, 980.0, 1820.0, 15)

# Landscape 1920x1080 (identity)
all_ok &= run_test("Landscape-Center", 1920, 1080, 960.0, 540.0, 8)
all_ok &= run_test("Landscape-Edge", 1920, 1080, 100.0, 100.0, 12)

# undo/redo
print("[Undo/Redo test]")
engine.newProject("UndoTest")
cid = engine.createComposition("UR", 1080, 1920, 30, 300)
engine.project.activeCompId = cid
comp = engine.activeTimeline
if not comp.tracks:
    comp.tracks.append(VideoTrack("v1"))

cmd1 = AddBrushStrokeCommand(engine, [{"x":300,"y":500}], 10, [1,1,1,1], 1.0)
cmd1.execute()
cmd2 = AddBrushStrokeCommand(engine, [{"x":600,"y":800}], 10, [1,1,1,1], 1.0)
cmd2.execute()

fd_before = _get_frame_data(0)
n_before = len([c for c in fd_before["clips"] if c["type"]=="pen"])
print(f"  Pen clips before undo: {n_before} (expected 2)")

cmd2.undo()
fd_after_undo = _get_frame_data(0)
n_undo = len([c for c in fd_after_undo["clips"] if c["type"]=="pen"])
print(f"  Pen clips after undo:  {n_undo} (expected 1)")

cmd2.redo() if hasattr(cmd2, "redo") else cmd2.execute()
fd_redo = _get_frame_data(0)
n_redo = len([c for c in fd_redo["clips"] if c["type"]=="pen"])
print(f"  Pen clips after redo:  {n_redo} (expected 2)")

undo_ok = n_before == 2 and n_undo == 1 and n_redo == 2
print(f"  Undo/Redo ==> {PASS if undo_ok else FAIL}")
all_ok &= undo_ok
print()

print("=" * 50)
print("ALL TESTS: " + (PASS if all_ok else FAIL))
print("=" * 50)

if not all_ok:
    sys.exit(1)
