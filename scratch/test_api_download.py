import urllib.request
import urllib.error
import json

data = json.dumps({"query": "short nature scenery", "numVideos": 1}).encode('utf-8')
req = urllib.request.Request(
    "http://127.0.0.1:8000/media/download-search",
    data=data,
    headers={'Content-Type': 'application/json'}
)

print("Calling POST /media/download-search ...")
try:
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read().decode())
        print("SUCCESS:")
        print(json.dumps(result, indent=2))
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body}")
except Exception as e:
    print(f"Error: {e}")
