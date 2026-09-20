import os
import sys
import shutil
from pathlib import Path
import yt_dlp

def _find_ffmpeg_dir() -> str | None:
    """Find ffmpeg directory for yt-dlp, works in dev and PyInstaller builds."""
     
    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).parent)
    if getattr(sys, 'frozen', False):
        _base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        for candidate in [
            _base / "renderer" / "build" / "Release",
            _base / "tools" / "ffmpeg",
        ]:
            if (candidate / "ffmpeg.exe").exists():
                return str(candidate)
    return None   

class YtdlpDownloader:
    def __init__(self):
        pass

    def search_and_download(
        self,
        query: str,
        num_videos: int = 2,
        output_dir: str = "",
        fps: float = 30.0,
    ) -> list[dict]:
        
        if not output_dir:
            output_dir = str(Path.home() / ".Fade" / "downloads")
        
        os.makedirs(output_dir, exist_ok=True)
        
        num_videos = max(1, min(num_videos, 5))
        search_query = f"ytsearch{num_videos}:{query}"
        
        fmt = (
            "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]"  # best h264 + aac  
            "/mp4[height<=720]"                                      
            "/mp4"                                                 
            "/best[ext=webm]"                                       
            "/best"                                                
        )

        _ffmpeg_dir = _find_ffmpeg_dir()

        ydl_opts = {
            'format': fmt,
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'noplaylist': True,
            # Don't abort if merge fails
            'ignoreerrors': False,
            # Windows fix: write directly to final filename — no .part temp file,
            # so yt-dlp never has to rename and WinError 32 cannot occur.
            'nopart': True,
            # If the final file already exists, overwrite it cleanly.
            'overwrites': True,
            # Extra retries on file-access errors (Windows file-lock races).
            'file_access_retries': 5,
        }
        if _ffmpeg_dir:
            ydl_opts['ffmpeg_location'] = _ffmpeg_dir


        results = []
        print(f"[YtdlpDownloader] Searching and downloading: {search_query}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=True)
            
            entries = info.get('entries', []) if 'entries' in info else [info]
            
            for entry in entries:
                if not entry:
                    continue
                
                filepath = entry.get('requested_downloads', [{}])[0].get('filepath')
                if not filepath:
                    filepath = ydl.prepare_filename(entry)
                     
                    if filepath:
                        base, ext = os.path.splitext(filepath)
                        if ext != '.mp4':
                            filepath = base + '.mp4'
                
                if filepath and os.path.exists(filepath):
                    results.append({
                        "filepath": filepath,
                        "title": entry.get("title", "Unknown"),
                        "duration_sec": float(entry.get("duration", 0) or 0.0)
                    })
                    
        return results
