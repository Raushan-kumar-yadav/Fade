import requests
import time

url = "http://localhost:8000/tracking/start"
payload = {
    "clip_id": "test1",
    "video_path": r"C:\Users\ariji\OneDrive\Desktop\fade test video.mp4",
    "from_frame": 3,
    "to_frame": 3,
    "detection_mode": "text",
    "text_pattern": "Gmail",
    "label": "test"
}
res = requests.post(url, json=payload)
print("Start response:", res.json())

job_id = res.json().get("job_id")
if job_id:
    for i in range(10):
        time.sleep(1)
        st = requests.get(f"http://localhost:8000/tracking/progress/{job_id}").json()
        print("Status:", st)
        if st.get("done") or st.get("error"):
            break
