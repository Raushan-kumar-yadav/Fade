import urllib.request
import json

data = json.dumps({"query": "test video short", "numVideos": 1}).encode('utf-8')
req = urllib.request.Request("http://127.0.0.1:8000/media/download-search", data=data, headers={'Content-Type': 'application/json'})

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode())
        print(json.dumps(result, indent=2))
except Exception as e:
    print(f"Error: {e}")
