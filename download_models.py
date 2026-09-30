"""
download_models.py
Downloads all AI models needed for Fade's tracking system into AIModels/.
Run once: python download_models.py
"""
import sys, os, io, zipfile, shutil
from pathlib import Path
import urllib.request

# Resolve AIModels/ relative to this script
SCRIPT_DIR  = Path(__file__).parent
AI_MODELS   = SCRIPT_DIR / "AIModels"
AI_MODELS.mkdir(exist_ok=True)

def progress_hook(url_label):
    def _hook(block, block_size, total):
        if total > 0:
            pct = min(100, block * block_size * 100 // total)
            print(f"\r  {url_label}: {pct}%", end="", flush=True)
    return _hook

def download(url: str, dest: Path, label: str):
    if dest.exists():
        print(f"  [ok] {label} already exists ({dest.name})")
        return
    print(f"  [dl] {label} ...")
    tmp = dest.with_suffix(".tmp")
    urllib.request.urlretrieve(url, tmp, reporthook=progress_hook(label))
    tmp.rename(dest)
    print(f"\n  [ok] {label} saved -> {dest.name}")

def download_zip(url: str, extract_name: str, dest: Path, label: str):
    """Download a .zip and extract a single file from it."""
    if dest.exists():
        print(f"  [ok] {label} already exists ({dest.name})")
        return
    print(f"  [dl] {label} (zip) ...")
    buf = io.BytesIO()
    with urllib.request.urlopen(url) as r:
        total = int(r.headers.get("Content-Length", 0))
        received = 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            buf.write(chunk)
            received += len(chunk)
            if total:
                pct = received * 100 // total
                print(f"\r  {label}: {pct}%", end="", flush=True)
    print()
    buf.seek(0)
    with zipfile.ZipFile(buf) as z:
        z.extract(extract_name, dest.parent)
    print(f"  [ok] {label} saved -> {dest.name}")


print("=" * 60)
print(" Fade AI Model Downloader")
print("=" * 60)

# ─── 1. YOLOv8n — person detection ───────────────────────────────────
print("\n[1/3] YOLOv8n (person detection)")
download(
    url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
    dest=AI_MODELS / "yolov8n.pt",
    label="yolov8n.pt",
)

# ─── 2. EasyOCR CRAFT — text detection ───────────────────────────────
print("\n[2/3] EasyOCR CRAFT (text region detection)")
download_zip(
    url="https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip",
    extract_name="craft_mlt_25k.pth",
    dest=AI_MODELS / "craft_mlt_25k.pth",
    label="craft_mlt_25k.pth",
)

# ─── 3. EasyOCR English recognition model ────────────────────────────
print("\n[3/3] EasyOCR English recognition model")
download_zip(
    url="https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip",
    extract_name="english_g2.pth",
    dest=AI_MODELS / "english_g2.pth",
    label="english_g2.pth",
)

# ─── Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(" Done! Files in AIModels/:")
for f in sorted(AI_MODELS.iterdir()):
    if f.is_file():
        mb = f.stat().st_size / 1_048_576
        print(f"   {f.name:35s}  {mb:7.1f} MB")
print("=" * 60)
print("\nNote: MediaPipe face models are bundled inside the mediapipe")
print("      package — no separate download needed.")
print("      For PyInstaller, add: --add-data 'AIModels;AIModels'")
