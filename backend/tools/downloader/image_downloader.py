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
        skip: int = 0,
        stride: int = 1,
    ) -> list[dict]:
        """
        Uses duckduckgo_search to find images and download them.
        Returns a list of dicts with filepath and title.

        skip / stride: only consider search results skip, skip+stride, skip+2*stride…
        Parallel jobs for the same query pass their own index as `skip` and the job
        count as `stride`, so each one downloads a different image and still has
        fallback candidates when a URL fails.
        """
        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "downloads")
        
        os.makedirs(output_dir, exist_ok=True)
        num_images = max(1, min(num_images, 10))
        skip = max(0, skip)
        stride = max(1, stride)
        # Fetch spare candidates: many image URLs are dead or block hotlinking.
        max_results = skip + stride * (num_images + 3)

        results = []
        print(f"[ImageDownloader] Searching images for: {query}")
        
        with DDGS() as ddgs:
            # Generate the search results
            try:
                # New ddgs API: query is positional
                search_results = list(ddgs.images(query, max_results=max_results))
            except TypeError:
                # Old duckduckgo_search API: keywords= kwarg
                search_results = list(ddgs.images(
                    keywords=query,
                    region="wt-wt",
                    safesearch="moderate",
                    size="Large",
                    max_results=max_results
                ))

            for i, result in list(enumerate(search_results))[skip::stride]:
                if len(results) >= num_images:
                    break
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
