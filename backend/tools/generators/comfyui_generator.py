 
from __future__ import annotations
import uuid
import time
import os
import json
from pathlib import Path

 
def _build_workflow(
    prompt: str,
    model_name: str,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg: float = 7.0,
    sampler: str = "euler",
    scheduler: str = "normal",
    seed: int | None = None,
) -> dict:
    """Build a minimal ComfyUI API-format workflow JSON."""
    if seed is None:
        import random
        seed = random.randint(0, 2**32 - 1)

    return {
        "3": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
            "class_type": "KSampler",
            "_meta": {"title": "KSampler"},
        },
        "4": {
            "inputs": {"ckpt_name": model_name},
            "class_type": "CheckpointLoaderSimple",
            "_meta": {"title": "Load Checkpoint"},
        },
        "5": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
            "class_type": "EmptyLatentImage",
            "_meta": {"title": "Empty Latent Image"},
        },
        "6": {
            "inputs": {
                "text": prompt,
                "clip": ["4", 1],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Positive Prompt"},
        },
        "7": {
            "inputs": {
                "text": "blurry, low quality, watermark, deformed, ugly",
                "clip": ["4", 1],
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Negative Prompt"},
        },
        "8": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2],
            },
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"},
        },
        "9": {
            "inputs": {
                "filename_prefix": "Fade_gen",
                "images": ["8", 0],
            },
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"},
        },
    }


# ComfyUI Client  

import threading as _threading
_start_lock = _threading.Lock()   

class ComfyUIImageGenerator:
     

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self._base_url = base_url.rstrip("/")
        self._client_id = str(uuid.uuid4())

    def _is_running(self) -> bool:
        """Quick liveness check."""
        import requests
        try:
            r = requests.get(f"{self._base_url}/system_stats", timeout=3)
            return r.ok
        except Exception:
            return False

    def _start_server(self, comfyui_path: str, timeout: int = 90) -> None:
         
        import subprocess, sys as _sys, requests

        comfyui_dir = Path(comfyui_path)
        main_py = comfyui_dir / "main.py"
        if not main_py.exists():
            raise FileNotFoundError(
                f"main.py not found in '{comfyui_path}'.\n"
                f"Make sure the ComfyUI Installation Folder points to the directory that "
                f"contains main.py (e.g. D:\\ComfyUI)."
            )

        with _start_lock:
            # Double-check 
            if self._is_running():
                print("[ComfyUI] Already running — skip start.", flush=True)
                return

            # Parse host/port from the base_url
            from urllib.parse import urlparse as _up
            parsed = _up(self._base_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port    or 8188

            cmd = [
                _sys.executable,         # same Python interpreter
                str(main_py),
                "--listen", host,
                "--port",   str(port),
            ]
            print(f"[ComfyUI] Starting: {' '.join(cmd)}", flush=True)

            # Start detached — we don't own its lifecycle
            subprocess.Popen(
                cmd,
                cwd=str(comfyui_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                # Windows: create new process group so it survives Fade restart
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )

        # Wait until ready
        print(f"[ComfyUI] Waiting for server to be ready (max {timeout}s)…", flush=True)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            try:
                r = requests.get(f"{self._base_url}/system_stats", timeout=3)
                if r.ok:
                    print("[ComfyUI] Server is ready ✓", flush=True)
                    return
            except Exception:
                pass
        raise RuntimeError(
            f"ComfyUI did not become ready within {timeout}s.\n"
            f"Check the terminal where ComfyUI is running for error messages."
        )

    def list_models(self) -> list[str]:
        """Return list of checkpoint model filenames installed in ComfyUI."""
        import requests
        try:
            r = requests.get(f"{self._base_url}/models/checkpoints", timeout=5)
            if r.ok:
                return r.json()
        except Exception:
            pass
        return []


    def generate(
        self,
        prompt: str,
        output_dir: str = "",
        model_name: str = "v1-5-pruned-emaonly.safetensors",
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg: float = 7.0,
        num_images: int = 1,
        comfyui_path: str = "",    
    ) -> list[dict]:
        """
        Generate images via ComfyUI.

        If ComfyUI is not running and *comfyui_path* points to the ComfyUI
        installation folder (the one that contains main.py), Fade will start
        it automatically and wait up to 90 s for it to be ready.

        Returns: [{"filepath": str, "title": str}]
        Raises:
            FileNotFoundError — comfyui_path set but main.py missing
            ConnectionError   — ComfyUI not running and no path configured
            RuntimeError      — workflow failed or timeout
        """
        import requests

        if not output_dir:
            output_dir = str(Path.home() / ".Fade" / "generations")
        os.makedirs(output_dir, exist_ok=True)

        if not self._is_running():
            if comfyui_path:
                # Auto-start from the configured folder
                self._start_server(comfyui_path)
            else:
                raise ConnectionError(
                    f"ComfyUI is not running at {self._base_url}.\n"
                    f"Either:\n"
                    f"  1. Set the ComfyUI Installation Folder in Settings → Generators → ComfyUI\n"
                    f"     and Fade will start it automatically.\n"
                    f"  2. Start it manually:\n"
                    f"     python main.py --listen 127.0.0.1 --port 8188"
                )


        # Verify model exists
        installed = self.list_models()
        if installed and not any(model_name in m for m in installed):
            # Use first available model as fallback
            if installed:
                fallback = installed[0]
                print(f"[ComfyUI] Model '{model_name}' not found, using '{fallback}'")
                model_name = fallback
            else:
                raise RuntimeError(
                    f"No checkpoint models found in ComfyUI.\n"
                    f"Download a model to:\n"
                    f"  D:\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\ComfyUI\\models\\checkpoints\n"
                    f"Recommended: v1-5-pruned-emaonly.safetensors (SD 1.5, ~2GB)"
                )

        results = []
        for i in range(num_images):
            print(f"[ComfyUI] Generating image {i+1}/{num_images} — model: {model_name}, prompt: {prompt[:60]}…")

            workflow = _build_workflow(
                prompt=prompt,
                model_name=model_name,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
            )

            # Submit workflow
            try:
                resp = requests.post(
                    f"{self._base_url}/prompt",
                    json={"prompt": workflow, "client_id": self._client_id},
                    timeout=15,
                )
                resp.raise_for_status()
                prompt_id = resp.json().get("prompt_id")
                if not prompt_id:
                    raise RuntimeError(f"ComfyUI did not return a prompt_id. Response: {resp.text[:200]}")

            except requests.HTTPError as e:
                raise RuntimeError(f"ComfyUI workflow submission failed: {e.response.status_code} {e.response.text[:200]}")

            print(f"[ComfyUI] Queued prompt_id={prompt_id}, polling…")

            # Poll for completion (max 3 minutes)
            max_wait = 180
            poll_interval = 2
            elapsed = 0

            while elapsed < max_wait:
                time.sleep(poll_interval)
                elapsed += poll_interval

                try:
                    hist_r = requests.get(
                        f"{self._base_url}/history/{prompt_id}", timeout=10
                    )
                    hist_r.raise_for_status()
                    history = hist_r.json()
                except Exception as e:
                    print(f"[ComfyUI] Poll error: {e}")
                    continue

                if prompt_id not in history:
                    continue  # still queued/running

                entry = history[prompt_id]
                status = entry.get("status", {})

                # Check for errors
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    raise RuntimeError(f"ComfyUI workflow errored: {messages}")

                # Find output images in node "9" (SaveImage)
                outputs = entry.get("outputs", {})
                images_found = []
                for node_id, node_output in outputs.items():
                    for img_info in node_output.get("images", []):
                        images_found.append(img_info)

                if not images_found:
                    continue  # not done yet

                # Download each image
                for img_info in images_found:
                    fname = img_info["filename"]
                    subfolder = img_info.get("subfolder", "")
                    img_type = img_info.get("type", "output")

                    params = {"filename": fname, "subfolder": subfolder, "type": img_type}
                    try:
                        img_r = requests.get(
                            f"{self._base_url}/view",
                            params=params,
                            timeout=30,
                        )
                        img_r.raise_for_status()
                    except Exception as e:
                        print(f"[ComfyUI] Failed to download image {fname}: {e}")
                        continue

                    out_filename = f"comfyui_{uuid.uuid4().hex[:10]}.png"
                    out_path = os.path.join(output_dir, out_filename)
                    with open(out_path, "wb") as f:
                        f.write(img_r.content)

                    print(f"[ComfyUI] Saved → {out_path} ({len(img_r.content)//1024}KB)")
                    results.append({"filepath": out_path, "title": f"AI: {prompt[:50]}"})
                    break  # one image per generation

                break  # done

            else:
                raise RuntimeError(f"ComfyUI generation timed out after {max_wait}s for prompt_id={prompt_id}")

        return results
