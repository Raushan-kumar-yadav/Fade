import requests
import json
import time

def trace_brush():
    print("========================================================")
    print("1. FRONTEND (Simulated)")
    print("========================================================")
    
    # Simulate drawing a horizontal line across the center
    # 1920x1080 canvas, center is roughly y=540, x from 500 to 1400
    points = [{"x": x, "y": 540} for x in range(500, 1400, 50)]
    size = 10.0
    color = [1.0, 1.0, 1.0, 1.0]
    
    print(f"pointerdown coords: {points[0]}")
    print(f"pointerup coords: {points[-1]}")
    print(f"final points.length: {len(points)}")
    
    payload = {
        "points": points,
        "size": size,
        "color": color,
        "opacity": 1.0
    }
    print("POST /editor/brush payload:")
    print(json.dumps(payload, indent=2))
    
    print("\n========================================================")
    print("2. POST RESPONSE")
    print("========================================================")
    
    try:
        r = requests.post("http://localhost:8000/editor/brush", json=payload)
    except Exception as e:
        print(f"Failed to connect to backend. Is it running? {e}")
        return
        
    print(f"HTTP status: {r.status_code}")
    
    try:
        data = r.json()
        print(f"Response body: {json.dumps(data, indent=2)}")
        clipId = data.get("clipId")
        print(f"returned clipId: {clipId}")
    except Exception as e:
        print(f"Failed to parse response: {e}")
        return
        
    print("\n========================================================")
    print("3. BACKEND CLIP")
    print("========================================================")
    
    # Get the timeline state to inspect the clip
    r = requests.get("http://localhost:8000/timeline/state")
    timeline = r.json()
    
    target_clip = None
    target_track = None
    track_idx = -1
    
    for i, track in enumerate(timeline.get("tracks", [])):
        for clip in track.get("clips", []):
            if clip.get("clipId") == clipId:
                target_clip = clip
                target_track = track
                track_idx = i
                break
                
    if not target_clip:
        print("Clip not found in timeline!")
        return
        
    print(f"clipId: {target_clip.get('clipId')}")
    print(f"track index: {track_idx}")
    print(f"track isAudio: {target_track.get('isAudio')}")
    print(f"clip type: {target_clip.get('type')}")
    print(f"clip start: {target_clip.get('startFrame')}")
    print(f"clip end: {target_clip.get('startFrame', 0) + target_clip.get('duration', 0)}")
    print(f"clip duration: {target_clip.get('duration')}")
    
    shapePath = target_clip.get("shapePath", {})
    vertices = shapePath.get("vertices", [])
    print(f"number of vertices: {len(vertices)}")
    if len(vertices) > 0:
        print(f"first vertex: {vertices[0]}")
        print(f"last vertex: {vertices[-1]}")
        
    style = target_clip.get("style", {})
    print(f"stroke width: {style.get('strokeWidth')}")
    print(f"stroke color: {style.get('strokeColor')}")
    
    transform = target_clip.get("transform", {})
    print(f"opacity: {transform.get('opacity', {}).get('baseValue')}")
    blend_mode_obj = target_clip.get("blendMode")
    if isinstance(blend_mode_obj, dict):
        print(f"blend mode: {blend_mode_obj.get('baseValue')}")
    else:
        print(f"blend mode: {blend_mode_obj}")
    
    print("\n========================================================")
    print("4. PATCH / POINT UPDATES")
    print("========================================================")
    print("No PATCH is expected with the new implementation, as the full array is sent on mouse-up.")
    
    print("\n========================================================")
    print("5. TIMELINE")
    print("========================================================")
    for i, track in enumerate(timeline.get("tracks", [])):
        print(f"Track {i}:")
        print(f"  name: {track.get('name')}")
        print(f"  isAudio: {track.get('isAudio')}")
        print(f"  clips: {len(track.get('clips', []))}")
        
    print(f"\nBrush clip:")
    print(f"  track index: {track_idx}")
    print(f"  clipId: {clipId}")
    
    print("\n========================================================")
    print("6. TIME RANGE — VERY IMPORTANT")
    print("========================================================")
    
    # Get current playhead frame from state
    current_frame = timeline.get("playheadFrame", 0)
    print(f"current playhead time: {current_frame}")
    print(f"clip.start: {target_clip.get('startFrame')}")
    print(f"clip.end: {target_clip.get('startFrame', 0) + target_clip.get('duration', 0)}")
    print(f"clip.duration: {target_clip.get('duration')}")
    
    end_frame = target_clip.get("startFrame", 0) + target_clip.get("duration", 0)
    
    is_active = target_clip.get("startFrame", 0) <= current_frame < end_frame
    print(f"is active at current playhead: {is_active}")
    
    print("\n========================================================")
    print("7. COMPOSITOR DAG (Simulated by calling /render/frame/3)")
    print("========================================================")
    
    r = requests.get(f"http://localhost:8000/render/frame/{current_frame}")
    frame_data = r.json()
    
    fd_clip = None
    for c in frame_data.get("clips", []):
        if c.get("clipId") == clipId:
            fd_clip = c
            break
            
    print(f"A. Does DAG construction see the Brush PenClip? {'Yes' if fd_clip else 'No'}")
    if fd_clip:
        pen_style = fd_clip.get("penStyle", {})
        pts = pen_style.get("points", [])
        print(f"E. How many vertices does draw_pen() receive? {len(pts)}")
        if len(pts) > 0:
            print(f"F. What coordinates does it receive? {pts[0]}")
        print(f"G. What stroke width does it receive? {pen_style.get('strokeWidth')}")
        print(f"H. What RGBA/color does it receive? {pen_style.get('strokeColor')}")
        print(f"I. What transform does it receive? {fd_clip.get('transform')}")
        print(f"J. Is the draw call actually executed? (Will check C++ side)")
        
    print("\n========================================================")
    print("9. VECTOR PEN COMPARISON")
    print("========================================================")
    
    vp_payload = {
        "startFrame": 0,
        "duration": 1800,
        "points": [{"x": 100, "y": 100, "inX": 0, "inY": 0, "outX": 0, "outY": 0}, 
                   {"x": 200, "y": 200, "inX": 0, "inY": 0, "outX": 0, "outY": 0}],
        "isClosed": False,
        "style": {}
    }
    r = requests.post("http://localhost:8000/clips/pen", json=vp_payload)
    vp_clip = r.json()
    
    print(f"                     BRUSH        VECTOR PEN")
    print(f"clip type           {target_clip.get('type'):12} {vp_clip.get('type')}")
    print(f"vertices            {len(vertices):<12} {len(vp_clip.get('shapePath', {}).get('vertices', []))}")
    
    vp_style = vp_clip.get("style", {})
    print(f"stroke width        {style.get('strokeWidth'):<12} {vp_style.get('strokeWidth')}")
    print(f"stroke color        {str(style.get('strokeColor')):<12} {str(vp_style.get('strokeColor'))}")
    print(f"fill opacity        {style.get('fillOpacity'):<12} {vp_style.get('fillOpacity')}")
    
if __name__ == '__main__':
    trace_brush()
