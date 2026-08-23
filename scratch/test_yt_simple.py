import yt_dlp
import os

def test():
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
        'merge_output_format': 'mp4',
        'ffmpeg_location': r'D:\ffmpeg\FFmpeg\ffmpeg.exe',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info("ytsearch1:test video short", download=True)

if __name__ == "__main__":
    test()
