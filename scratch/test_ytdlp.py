import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

# Add ffmpeg to PATH for yt-dlp merging
_FFMPEG_DIRS = [r"D:\ffmpeg\FFmpeg", r"D:\ffmpeg\FFmpeg\bin"]
for _d in _FFMPEG_DIRS:
    if os.path.isdir(_d) and _d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")

from backend.tools.downloader.ytdlp_downloader import YtdlpDownloader

def test():
    print("Testing YtdlpDownloader...")
    downloader = YtdlpDownloader()
    
    results = downloader.search_and_download(
        query="test video short", 
        num_videos=1,
        fps=30.0
    )
    
    print("\nResults:")
    for r in results:
        print(f"Title: {r.get('title')}")
        print(f"Filepath: {r.get('filepath')}")
        print(f"Duration: {r.get('duration_sec')} sec")
        
if __name__ == "__main__":
    test()
