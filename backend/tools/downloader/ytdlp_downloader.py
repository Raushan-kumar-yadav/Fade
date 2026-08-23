import os
from pathlib import Path
import yt_dlp

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
            output_dir = str(Path.home() / ".fade" / "downloads")
        
        os.makedirs(output_dir, exist_ok=True)
        
        num_videos = max(1, min(num_videos, 5))
        search_query = f"ytsearch{num_videos}:{query}"
        
        
        fmt = (
            "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]"  # best h264 + aac (needs merge)
            "/mp4[height<=720]"                                      
            "/mp4"                                                 
            "/best[ext=webm]"                                       
            "/best"                                                
        )

        # Point yt-dlp 
        _FFMPEG = r"C:\Users\raush\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin"

        ydl_opts = {
            'format': fmt,
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'ffmpeg_location': _FFMPEG,
            # Don't abort if merge fails  
            'ignoreerrors': False,
        }

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
