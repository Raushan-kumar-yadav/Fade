import requests
try:
    print(requests.get("http://127.0.0.1:8000/timeline/audio-clips").json())
except Exception as e:
    print(e)
