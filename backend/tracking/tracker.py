import cv2
import numpy as np
from backend.media.decoder.videoDecoder import VideoDecoder

def run_tracking(filepath: str, fps: float, start_frame: int, end_frame: int, initial_bbox: tuple[float, float, float, float], progress_callback=None) -> dict:
    """
    Runs cv2 MIL tracker.
    Returns: { "frames": { "frameNumber": {"x": cx, "y": cy, "w": w, "h": h} } }
    """
    tracker = cv2.TrackerMIL_create()

    decoder = VideoDecoder(filepath, fps, scale_factor=1.0)
    frames_data = {}

    frame = decoder.decodeFrame(start_frame)
    if not frame or not frame.valid:
        decoder.close()
        raise ValueError(f"Could not decode start frame {start_frame}")

    arr = np.frombuffer(frame.dataRGBA, dtype=np.uint8).reshape((frame.height, frame.width, 4))
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

    bbox_int = (int(initial_bbox[0]), int(initial_bbox[1]), int(initial_bbox[2]), int(initial_bbox[3]))
    try:
        tracker.init(bgr, bbox_int)
    except Exception as e:
        decoder.close()
        raise ValueError(f"Failed to initialize tracker: {e}")

    center_x = initial_bbox[0] + initial_bbox[2] / 2
    center_y = initial_bbox[1] + initial_bbox[3] / 2
    frames_data[str(start_frame)] = {"x": center_x, "y": center_y, "w": initial_bbox[2], "h": initial_bbox[3]}

    for f in range(start_frame + 1, end_frame + 1):
        if progress_callback:
            if not progress_callback(f, end_frame):
                break
        frame = decoder.decodeFrame(f)
        if not frame or not frame.valid:
            break

        arr = np.frombuffer(frame.dataRGBA, dtype=np.uint8).reshape((frame.height, frame.width, 4))
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

        ok, bbox = tracker.update(bgr)
        if ok:
            cx = bbox[0] + bbox[2] / 2
            cy = bbox[1] + bbox[3] / 2
            frames_data[str(f)] = {"x": cx, "y": cy, "w": bbox[2], "h": bbox[3]}
        else:
            break

    decoder.close()
    return frames_data
