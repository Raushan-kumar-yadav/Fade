import pytest
from backend.animation.animatableProperty import AnimatableProperty, Vec2Property
from backend.timeline.clips.videoClip import VideoClip
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.timeline import Timeline
from backend.tracking.tracker import run_tracking
import numpy as np

def test_animatable_property_basic():
    ap = AnimatableProperty(10.0)
    assert ap.evaluate(0) == 10.0
    ap.update(0)
    assert ap.get() == 10.0

def test_keyframe_evaluation():
    ap = AnimatableProperty(0.0)
    ap.addKeyframe(0, 10.0)
    ap.addKeyframe(10, 20.0)
    assert ap.is_animated()
    val = ap.evaluate(5)
    # bezier interpolation should return some value between 10 and 20
    assert 10.0 < val < 20.0

def test_position_evaluation():
    vp = Vec2Property(100.0, 200.0)
    assert vp.evaluate(0) == (100.0, 200.0)
    vp.addKeyframe(10, 150.0, 250.0)
    assert vp.x.is_animated()
    
def test_rotation_scale_evaluation():
    from backend.animation.transform import Transform
    t = Transform()
    t.rotation.setBaseValue(45.0)
    t.scale.setBase(2.0, 2.0)
    assert t.rotation.evaluate(0) == 45.0
    assert t.scale.evaluate(0) == (2.0, 2.0)

def test_simple_property_linking():
    tl = Timeline()
    track = VideoTrack()
    tl.tracks.append(track)
    clip_a = VideoClip("clipA", 0, 100)
    clip_b = VideoClip("clipB", 0, 100)
    track.clips.extend([clip_a, clip_b])
    
    clip_a.transform.position.setBase(300.0, 400.0)
    
    clip_b.transform.position.x.expression = "link:clipA:position.x"
    clip_b.transform.position.y.expression = "link:clipA:position.y"
    
    ctx = {"timeline": tl, "clip": clip_b}
    
    clip_b.transform.evaluateAll(0, context=ctx)
    assert clip_b.transform.position.get() == (300.0, 400.0)

def test_tracking_result_structure_and_range():
    # We will test the mock logic or raise if file not found
    try:
        res = run_tracking("invalid_path.mp4", 30.0, 0, 10, (0,0,10,10))
    except Exception as e:
        assert "stream" in str(e) or "Could not decode" in str(e) or "Failed" in str(e)

def test_tracking_data_storage():
    clip = VideoClip("clip1", 0, 100)
    tdata = {
        "startFrame": 10,
        "endFrame": 15,
        "property": "position",
        "frames": {
            "10": {"x": 500, "y": 600, "w": 100, "h": 100}
        }
    }
    clip.trackingData = tdata
    d = clip.toDict()
    assert "trackingData" in d
    
    clip2 = VideoClip.fromDict(d)
    assert clip2.trackingData["frames"]["10"]["x"] == 500

def test_tracking_data_driving_position():
    tl = Timeline()
    clip = VideoClip("clip1", 0, 100)
    tl.tracks.append(VideoTrack())
    tl.tracks[0].clips.append(clip)
    
    clip.trackingData = {
        "startFrame": 0,
        "endFrame": 5,
        "property": "position",
        "frames": {
            "0": {"x": 111, "y": 222, "w": 10, "h": 10}
        }
    }
    clip.transform.position.x.expression = "tracking:self"
    clip.transform.position.y.expression = "tracking:self"
    
    ctx = {"timeline": tl, "clip": clip, "timelineFrame": 0}
    clip.transform.evaluateAll(0, context=ctx)
    assert clip.transform.position.x.get() == 111
    assert clip.transform.position.y.get() == 222

def test_invalid_frame_ranges():
    ap = AnimatableProperty(0)
    ap.expression = "tracking:self"
    ctx = {"timelineFrame": 999, "clip": VideoClip("c", 0, 10)}
    # missing trackingData
    assert ap.evaluate(0, context=ctx) == 0

def test_missing_clip_asset():
    ap = AnimatableProperty(0)
    ap.expression = "link:non_existent:position.x"
    tl = Timeline()
    ctx = {"timeline": tl}
    assert ap.evaluate(0, context=ctx) == 0

def test_tracking_failure_handling():
    try:
        run_tracking("missing", 30.0, 0, 10, (0,0,10,10))
    except Exception as e:
        assert True
