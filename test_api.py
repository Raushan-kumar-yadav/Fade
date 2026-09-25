import requests
import time

print("Creating brush stroke...")
res = requests.post("http://localhost:8000/editor/brush", json={
    "points": [{"x": 100, "y": 100}],
    "size": 15,
    "color": [1, 0, 0, 1]
})
print(res.json())
