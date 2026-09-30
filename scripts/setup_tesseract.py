"""
scripts/setup_tesseract.py
==========================
Auto-downloads portable Tesseract 5.4 (Windows) into AIModels/tesseract/.
Safe to run multiple times — skips if already present.
"""
from __future__ import annotations
import os, sys, shutil, tempfile, subprocess, urllib.request
from pathlib import Path

TESS_VERSION = "5.4.0.20240606"
TESS_URL = (
    f"https://github.com/UB-Mannheim/tesseract/releases/download/"
    f"v{TESS_VERSION}/tesseract-ocr-w64-setup-{TESS_VERSION}.exe"
)
REPO_ROOT = Path(__file__).resolve().parent.parent
TESS_DIR  = REPO_ROOT / "AIModels" / "tesseract"
TESS_EXE  = TESS_DIR  / "tesseract.exe"


def _find_7z():
    for c in ["7z", r"C:\Program Files\7-Zip\7z.exe"]:
        if shutil.which(c) or Path(c).is_file():
            return c
    return None


def _download(url, dest):
    print(f"[Tesseract] Downloading {url.split('/')[-1]} ...", flush=True)
    def _prog(b, bs, total):
        if total > 0:
            print(f"\r[Tesseract] {min(100, b*bs*100//total)}%  ", end="", flush=True)
    urllib.request.urlretrieve(url, dest, reporthook=_prog)
    print(f"\r[Tesseract] Downloaded {Path(dest).stat().st_size//1048576} MB", flush=True)


def ensure_tesseract() -> bool:
    if TESS_EXE.is_file():
        return True
    if sys.platform != "win32":
        return bool(shutil.which("tesseract"))

    seven_z = _find_7z()
    if not seven_z:
        print("[Tesseract] 7-Zip not found. Install from https://www.7-zip.org/", flush=True)
        return False

    installer = Path(tempfile.gettempdir()) / f"tesseract-setup-{TESS_VERSION}.exe"
    try:
        if not installer.is_file():
            _download(TESS_URL, installer)
        TESS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[Tesseract] Extracting to {TESS_DIR} ...", flush=True)
        subprocess.run([seven_z, "e", str(installer), f"-o{TESS_DIR}", "-y", "*.exe", "*.dll"],
                       capture_output=True)
        ok = TESS_EXE.is_file()
        print(f"[Tesseract] {'✓ ready' if ok else '✗ extraction failed'}", flush=True)
        return ok
    except Exception as e:
        print(f"[Tesseract] Setup error: {e}", flush=True)
        return False


if __name__ == "__main__":
    sys.exit(0 if ensure_tesseract() else 1)
