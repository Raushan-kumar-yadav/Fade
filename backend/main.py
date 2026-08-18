from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import socket

app = FastAPI(title="Fade Backend")

app.add_middleware(CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/health")
def health():
    return {"status": "ok"}

def find_free_port(start: int = 8000, end: int = 8010) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found between {start} and {end}")

if __name__ == "__main__":
    port = find_free_port()
    print(f"[Fade] Starting backend on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
