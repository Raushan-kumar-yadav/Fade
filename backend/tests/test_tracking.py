import pytest
import time
from backend.state import engine, _library
from backend.project.project import Project
from backend.timeline.timeline import Timeline
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.clips.videoClip import VideoClip
from backend.timeline.clips.textClip import TextClip
from backend.media.asset.mediaAsset import MediaAsset
from backend.animation.animatableProperty import AnimatableProperty, Vec2Property
from backend.routers.jobs import _make_job, _get_job, is_job_cancelled, _update_job, _start
from backend.tracking.tracker import run_tracking
from backend.routers.tracking import start_tracking, TrackRequest, bind_tracking, BindTrackingRequest

@pytest.fixture(autouse=True)
def setup_engine():
    proj = Project("TestProject")
    engine.project = proj
    tl = Timeline()
    proj.timelines.append(tl)

    asset = MediaAsset("dummy.mp4", "asset_123")
    _library["asset_123"] = asset

    track = VideoTrack()
    tl.tracks.append(track)

    clip = VideoClip('clip_123', startFrame=100, duration=50, assetId='asset_123', mediaOffset=5)
    clip.filepath = 'dummy.mp4'
    track.clips.append(clip)

    yield
    _library.clear()
    engine.project = None
    engine.commandStack._undoStack.clear()

def test_asset_storage_and_serialization():
    asset = _library["asset_123"]
    asset.trackingResults["track_001"] = {
        "id": "track_001",
        "startFrame": 0,
        "endFrame": 5,
        "frames": {"0": {"x": 100, "y": 200}}
    }

    d = asset.toDict()
    assert "trackingResults" in d
    assert d["trackingResults"]["track_001"]["frames"]["0"]["x"] == 100

    asset2 = MediaAsset.fromDict(d)
    assert asset2.trackingResults["track_001"]["frames"]["0"]["y"] == 200

def test_clip_source_frame_mapping():
    tl = engine.project.timelines[0]
    clip = tl.tracks[0].clips[0]

    # Clip starts at timeline frame 100, and mediaOffset is 5.
    # At timeline frame 100, sourceFrame should be 5.
    # At timeline frame 110, sourceFrame should be 15.
    assert clip.sourceFrame(100) == 5
    assert clip.sourceFrame(110) == 15

def test_expression_context_tracking_access():
    tl = engine.project.timelines[0]
    clip = tl.tracks[0].clips[0]
    asset = _library["asset_123"]

    # Add fake tracking data to asset
    asset.trackingResults["track_001"] = {
        "id": "track_001",
        "frames": {
            "5": {"x": 555, "y": 666},
            "15": {"x": 777, "y": 888}
        }
    }

    # Evaluate at timeline frame 100
    from backend.animation.expression_context import build_context
    ctx = build_context(100, 0.0, clip, tl)

    # In JS: this.tracking("track_001").x
    result_x = eval("this.tracking('track_001').x", {}, ctx)
    assert result_x == 555.0

    ctx2 = build_context(110, 0.0, clip, tl)
    result_y = eval("this.tracking('track_001').y", {}, ctx2)
    assert result_y == 888.0

def test_cross_clip_tracking_access():
    tl = engine.project.timelines[0]
    # Add a text clip that doesn't have an asset, but references the video clip's tracking
    text_clip = TextClip("text_1", startFrame=100, duration=10)
    tl.tracks[0].clips.append(text_clip)

    asset = _library["asset_123"]
    asset.trackingResults["track_001"] = {
        "id": "track_001",
        "frames": {
            "15": {"x": 42, "y": 24}
        }
    }

    from backend.animation.expression_context import build_context
    ctx = build_context(110, 0.0, text_clip, tl)

    # In JS: comp.clip("clip_123").tracking("track_001").x
    result_x = eval("comp.clip('clip_123').tracking('track_001').x", {}, ctx)
    assert result_x == 42.0

def test_bind_expression_command():
    tl = engine.project.timelines[0]
    clip = tl.tracks[0].clips[0]

    req = BindTrackingRequest(
        clip_id="clip_123",
        property_name="position",
        expression="this.tracking('track_999')"
    )
    bind_tracking(req)

    assert clip.transform.position.expression == "this.tracking('track_999')"
    assert clip.transform.position.x.get_expression() == "this.tracking('track_999').x"

def test_job_queue_creation_and_progress():
    # We will just test that start_tracking creates a job correctly
    # Note: since the actual tracker uses OpenCV and reads a file, we expect it to fail gracefully if the file is missing,
    # but the job should still be created and returned.
    req = TrackRequest(
        clip_id="clip_123",
        start_frame=100,
        end_frame=110,
        property="position",
        x=0, y=0, width=100, height=100
    )

    res = start_tracking(req)
    assert res["success"] is True
    job_id = res["jobId"]
    assert job_id is not None

    job = _get_job(job_id)
    assert job["status"] in ("pending", "running", "error") # error if opencv fails to load dummy.mp4 instantly
    assert job["assetId"] == "asset_123"

def test_invalid_clip_id():
    req = TrackRequest(
        clip_id="invalid",
        start_frame=100,
        end_frame=110,
        property="position",
        x=0, y=0, width=100, height=100
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        start_tracking(req)

def test_clip_results_summary_endpoint():
    from backend.routers.tracking import get_clip_tracking_results
    asset = _library["asset_123"]
    if not hasattr(asset, "trackingResults"):
        asset.trackingResults = {}
    asset.trackingResults["track_002"] = {
        "id": "track_002",
        "startFrame": 0,
        "endFrame": 5,
        "frames": {"0": {"x": 100, "y": 200}},
        "targetText": "hello",
        "targetType": "text",
        "property": "position",
        "sourceClipId": "clip_123"
    }
    
    results = get_clip_tracking_results("clip_123")
    assert "track_002" in results
    summary = results["track_002"]
    assert summary["targetText"] == "hello"
    assert summary["targetType"] == "text"
    assert summary["frameCount"] == 1
    assert "frames" not in summary


def test_tracking_global_projection():
    from backend.timeline.clips.textClip import TextClip
    from backend.media.asset.mediaAsset import MediaAsset
    # Native asset is 1280x720
    asset = _library["asset_123"]
    asset.width = 1280
    asset.height = 720
    
    # Tracked point at (100, 200) in native space
    asset.trackingResults["track_001"] = {
        "id": "track_001",
        "frames": {
            "10": {"x": 100, "y": 200},
            "11": {"x": 110, "y": 210}  # scrub movement
        }
    }
    
    tl = engine.project.timelines[0]
    tl.tracks[0].clips.clear()
    
    # Video clip with custom transform
    vclip = VideoClip("clip_vid", startFrame=10, duration=10, assetId="asset_123")
    # MediaOffset is 0. sourceFrame(10) = 0. We need sourceFrame(10) to map to asset frame 10.
    vclip.mediaOffset = 10
    
    # Give the video clip a transform
    vclip.transform.position.setBase(100.0, 50.0)
    
    vclip.transform.scale.setBase(2.0, 2.0)
    
    tl.tracks[0].clips.append(vclip)
    
    tclip = TextClip("text_1", startFrame=10, duration=10)
    tl.tracks[0].clips.append(tclip)
    
    from backend.animation.expression_context import build_context
    ctx = build_context(10, 0.0, tclip, tl)
    result_x = eval("comp.clip('clip_vid').tracking('track_001').x", {}, ctx)
    result_y = eval("comp.clip('clip_vid').tracking('track_001').y", {}, ctx)
    
    assert result_x == -560.0
    assert result_y == 110.0
    
    # 2) Scrubbing evaluation changes coordinates
    ctx2 = build_context(11, 0.0, tclip, tl)
    result_x2 = eval("comp.clip('clip_vid').tracking('track_001').x", {}, ctx2)
    assert result_x2 == -530.0






def test_tracking_video_clip_projection():
    from backend.timeline.clips.videoClip import VideoClip
    from backend.media.asset.mediaAsset import MediaAsset
    asset = MediaAsset("test.mp4", "asset_123")
    asset.width = 1280
    asset.height = 720
    _library["asset_123"] = asset
    
    asset.trackingResults["track_001"] = {
        "id": "track_001",
        "frames": {
            "10": {"x": 100, "y": 200},
            "11": {"x": 110, "y": 210}
        }
    }
    
    tl = engine.project.timelines[0]
    tl.tracks[0].clips.clear()
    
    vclip = VideoClip("clip_vid", startFrame=10, duration=10, assetId="asset_123")
    vclip.mediaOffset = 10
    vclip.transform.position.setBase(100.0, 50.0)
    vclip.transform.scale.setBase(2.0, 2.0)
    tl.tracks[0].clips.append(vclip)
    
    target_vid = VideoClip('target', startFrame=10, duration=10)
    tl.tracks[0].clips.append(target_vid)
    
    from backend.animation.expression_context import build_context
    ctx = build_context(10, 0.0, target_vid, tl)
    
    result_x = eval('comp.clip(\"clip_vid\").tracking(\"track_001\").x', {}, ctx)
    result_y = eval('comp.clip(\"clip_vid\").tracking(\"track_001\").y', {}, ctx)
    
    assert result_x == -560.0 - 960.0
    assert result_y == 110.0 - 540.0
