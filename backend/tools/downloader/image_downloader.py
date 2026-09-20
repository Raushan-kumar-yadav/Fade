import os
import requests
from pathlib import Path
try:
    from ddgs import DDGS  # new package name
except ImportError:
    from duckduckgo_search import DDGS  # old package name fallback
from urllib.parse import urlparse

class ImageDownloader:
    def __init__(self):
        pass
        
    def _get_ext_from_url(self, url: str) -> str:
        """Extract extension from url, defaulting to .jpg"""
        path = urlparse(url).path
        ext = os.path.splitext(path)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}:
            return ext
        return ".jpg"

    def search_and_download(
        self,
        query: str,
        num_images: int = 2,
        output_dir: str = "",
    ) -> list[dict]:
        """
        Uses duckduckgo_search to find images and download them.
        Returns a list of dicts with filepath and title.
        """
        if not output_dir:
            output_dir = str(Path.home() / ".Fade" / "downloads")
        
        os.makedirs(output_dir, exist_ok=True)
        num_images = max(1, min(num_images, 10))
        
        results = []
        print(f"[ImageDownloader] Searching images for: {query}")
        
        with DDGS() as ddgs:
            # Generate the search results
            try:
                # New ddgs API: query is positional
                search_results = list(ddgs.images(query, max_results=num_images))
            except TypeError:
                # Old duckduckgo_search API: keywords= kwarg
                search_results = list(ddgs.images(
                    keywords=query,
                    region="wt-wt",
                    safesearch="moderate",
                    size="Large",
                    max_results=num_images
                ))
            
            for i, result in enumerate(search_results):
                image_url = result.get('image')
                title = result.get('title', f"image_{i}")
                
                if not image_url:
                    continue
                    
                # Clean up title for filename
                safe_title = "".join(c if c.isalnum() else "_" for c in title)[:50].strip("_")
                if not safe_title:
                    safe_title = f"image_{i}"
                    
                ext = self._get_ext_from_url(image_url)
                filename = f"{safe_title}{ext}"
                filepath = os.path.join(output_dir, filename)
                
                # Download the image
                try:
                    print(f"[ImageDownloader] Downloading {image_url}")
                    response = requests.get(image_url, timeout=10)
                    response.raise_for_status()
                    
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                        
                    results.append({
                        "filepath": filepath,
                        "title": title
                    })
                except Exception as e:
                    print(f"[ImageDownloader] Failed to download {image_url}: {e}")
                    
        return results
