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
