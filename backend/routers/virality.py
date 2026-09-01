 

from __future__ import annotations
import os
import sys
import json
import sqlite3
import threading
import base64
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from io import BytesIO
from typing import Optional, List
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

#   SQLite DB  

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "virality.db"
_db_lock = threading.Lock()


@contextmanager
def _db():
    with _db_lock:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _init_db():
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id      INTEGER PRIMARY KEY DEFAULT 1,
            name    TEXT    DEFAULT '',
            email   TEXT    DEFAULT '',
            bio     TEXT    DEFAULT '',
            avatar  TEXT    DEFAULT ''
        );

        INSERT OR IGNORE INTO user_profile (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS connections (
            platform        TEXT PRIMARY KEY,
            access_token    TEXT DEFAULT '',
            refresh_token   TEXT DEFAULT '',
            channel_id      TEXT DEFAULT '',
            channel_name    TEXT DEFAULT '',
            expires_at      INTEGER DEFAULT 0,
            connected       INTEGER DEFAULT 0
        );

        INSERT OR IGNORE INTO connections (platform) VALUES ('youtube');
        INSERT OR IGNORE INTO connections (platform) VALUES ('instagram');
        """)


_init_db()

#   Model Pipeline  

_pipeline = None
_pipeline_lock = threading.Lock()
_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "AIModels" / "SIH_Virality_Prototype" / "models"
_PIPELINE_SRC = Path(__file__).resolve().parent.parent.parent / "AIModels" / "SIH_Virality_Prototype"


def _get_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        try:
            # Add prototype dir to sys.path so model_pipeline.py can import
            src = str(_PIPELINE_SRC)
            if src not in sys.path:
                sys.path.insert(0, src)
            from model_pipeline import SIHPipeline  # type: ignore
            _pipeline = SIHPipeline(str(_MODELS_DIR))
            print("[Virality] SIHPipeline loaded.", flush=True)
        except Exception as exc:
            print(f"[Virality] SIHPipeline load failed: {exc}", flush=True)
            _pipeline = None
    return _pipeline


#   LLM helper  

_llm_cache = None
_llm_cache_lock = threading.Lock()

def _get_llm():
    """Return the same LangChain LLM used by the AI agent (lazily cached)."""
    global _llm_cache
    if _llm_cache is not None:
        return _llm_cache
    with _llm_cache_lock:
        if _llm_cache is not None:
            return _llm_cache
        from backend.ai.agent import _build_llm  # type: ignore
        _llm_cache = _build_llm()
    return _llm_cache


def _call_llm(prompt: str) -> str:
    """Call the configured LLM (same provider as the AI agent) and return the text."""
    llm = _get_llm()
    from langchain_core.messages import HumanMessage  # type: ignore
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content



#   YouTube helpers  
def _get_youtube_credentials():
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass
    return (
        os.environ.get("YOUTUBE_CLIENT_ID", ""),
        os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    )

_YT_API_KEY = os.environ.get("YOUTUBE_API_KEY",       "")
_REDIRECT_URI = "http://127.0.0.1:8000/virality/youtube/oauth2callback"

YOUTUBE_SCOPES = "https://www.googleapis.com/auth/youtube"


def _yt_api_get(path: str, params: dict, access_token: str = "") -> dict:
    """Simple GET wrapper for YouTube Data API v3.

    If access_token starts with 'AIza' it is actually a Data API key
    (quick-connect mode) — use key= instead of access_token=.
    Raises HTTPException with a descriptive message on API errors.
    """
    base = "https://www.googleapis.com/youtube/v3"
    p = dict(params)  # don't mutate caller's dict
    if access_token and access_token.startswith("AIza"):
        p["key"] = access_token
    elif access_token:
        p["access_token"] = access_token
    elif _YT_API_KEY:
        p["key"] = _YT_API_KEY
    else:
        raise HTTPException(400, "No YouTube API key or access token available")
    url = f"{base}{path}?" + urllib.parse.urlencode(p)

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Try to extract YouTube's own error message from the response body
        try:
            body = json.loads(e.read().decode())
            yt_msg = body.get("error", {}).get("message", str(e))
            yt_reason = body.get("error", {}).get("errors", [{}])[0].get("reason", "")
        except Exception:
            yt_msg = str(e)
            yt_reason = ""

        detail = f"YouTube API error {e.code}: {yt_msg}"
        if e.code == 403:
            if "accessNotConfigured" in yt_reason or "disabled" in yt_msg.lower():
                detail = ("YouTube Data API v3 is not enabled on this project. "
                          "Go to console.cloud.google.com → APIs & Services → "
                          "Library → search 'YouTube Data API v3' → Enable it.")
            elif yt_reason in ("keyInvalid", "badRequest"):
                detail = "Invalid API key. Double-check you copied the full key."
            else:
                detail = (f"403 Forbidden ({yt_reason or 'unknown reason'}). "
                          "Your API key may have HTTP Referrer restrictions — "
                          "in Google Cloud Console, edit the key and set restriction "
                          "to 'None' or 'IP addresses' instead of HTTP referrers.")
        raise HTTPException(403, detail)
    except urllib.error.URLError as e:
        raise HTTPException(502, f"Network error reaching YouTube API: {e.reason}")


def _fetch_yt_thumbnail_bytes(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()
    except Exception:
        return b""


def _refresh_yt_access_token(refresh_token: str) -> str:
    """Exchange a refresh_token for a fresh access_token via Google OAuth2.
    Returns the new access_token string, or empty string on failure.
    Updates the DB row automatically on success.
    """
    client_id, client_secret = _get_youtube_credentials()
    if not refresh_token or not client_id or not client_secret:
        return ""
    try:
        body = urllib.parse.urlencode({
            "client_id":     client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type":    "refresh_token",
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            info = json.loads(resp.read())
        new_token = info.get("access_token", "")
        if new_token:
            with _db() as conn:
                conn.execute(
                    "UPDATE connections SET access_token=? WHERE platform='youtube'",
                    (new_token,)
                )
            print("[Virality] OAuth token auto-refreshed.", flush=True)
        return new_token
    except Exception as exc:
        print(f"[Virality] Token refresh failed: {exc}", flush=True)
        return ""


def _fetch_latest_yt_videos(channel_id: str, access_token: str) -> list:
    """Return top-10 latest videos for a channel with all info the model needs."""
    try:
        # Get upload playlist ID
        ch = _yt_api_get("/channels", {"id": channel_id, "part": "contentDetails,statistics"}, access_token)
        items = ch.get("items", [])
        if not items:
            return []
        uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        ch_stats = items[0].get("statistics", {})
        baseline_views = int(ch_stats.get("viewCount", 10000)) // max(1, int(ch_stats.get("videoCount", 1)))

        # Get playlist items
        pl = _yt_api_get("/playlistItems", {
            "playlistId": uploads_playlist,
            "part": "snippet,contentDetails",
            "maxResults": 10,
        }, access_token)

        video_ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        if not video_ids:
            return []

        # Get full video details
        vd = _yt_api_get("/videos", {
            "id": ",".join(video_ids),
            "part": "snippet,statistics,contentDetails",
        }, access_token)

        result = []
        for item in vd.get("items", []):
            snip = item["snippet"]
            stats = item.get("statistics", {})
            thumb_url = (snip.get("thumbnails", {}).get("high") or
                         snip.get("thumbnails", {}).get("medium") or
                         snip.get("thumbnails", {}).get("default") or {}).get("url", "")
            result.append({
                "videoId": item["id"],
                "title": snip.get("title", ""),
                "description": snip.get("description", "")[:300],
                "publishedAt": snip.get("publishedAt", ""),
                "category": snip.get("categoryId", "Entertainment"),  # numeric, mapped below
                "thumbUrl": thumb_url,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration": item.get("contentDetails", {}).get("duration", "PT0S"),
                "baselineViews": baseline_views,
                "platform": "youtube",
            })
        return result
    except Exception as exc:
        print(f"[Virality] YT fetch error: {exc}", flush=True)
        return []


_YT_CATEGORY_MAP = {
    "1": "Film & Animation", "2": "Autos & Vehicles", "10": "Music",
    "15": "Pets & Animals", "17": "Sports", "18": "Short Movies",
    "19": "Travel & Events", "20": "Gaming", "21": "Videoblogging",
    "22": "People & Blogs", "23": "Comedy", "24": "Entertainment",
    "25": "News & Politics", "26": "Howto & Style", "27": "Education",
    "28": "Science & Technology", "29": "Nonprofits & Activism",
}

_MODEL_CATEGORIES = [
    "Entertainment", "Education", "Gaming", "People & Blogs",
    "Science & Technology", "Instagram_Content",
]


def _map_yt_category(cat_id: str) -> str:
    full = _YT_CATEGORY_MAP.get(str(cat_id), "Entertainment")
    # Map to model's known categories
    for mc in _MODEL_CATEGORIES:
        if mc.lower() in full.lower() or full.lower() in mc.lower():
            return mc
    return "Entertainment"


# Pydantic models  

class ProfileUpdate(BaseModel):
    name: str = ""
    email:  str = ""
    bio: str = ""
    avatar: str = ""    # base64 data URL or empty


class YTTokens(BaseModel):
    access_token:  str
    refresh_token: str = ""
    channel_id: str = ""
    channel_name:  str = ""
    expires_at: int = 0


class IGTokens(BaseModel):
    access_token: str
    user_id: str = ""
    username: str = ""


class AnalyzeRequest(BaseModel):
    videoId: str
    title: str
    thumbUrl: str
    platform: str = "youtube"
    category: str = "Entertainment"
    baselineViews: int = 10000


#   Profile endpoints  

@router.get("/virality/profile")
def get_profile():
    with _db() as conn:
        row = conn.execute("SELECT * FROM user_profile WHERE id=1").fetchone()
        return dict(row) if row else {}


@router.post("/virality/profile")
def save_profile(req: ProfileUpdate):
    with _db() as conn:
        conn.execute("""
            UPDATE user_profile SET name=?, email=?, bio=?, avatar=? WHERE id=1
        """, (req.name, req.email, req.bio, req.avatar))
    return {"ok": True}


#   Connection endpoints  

@router.get("/virality/connections")
def get_connections():
    with _db() as conn:
        rows = conn.execute("SELECT * FROM connections").fetchall()
        return {row["platform"]: dict(row) for row in rows}


@router.get("/virality/youtube/auth-url")
def youtube_auth_url():
    client_id, _ = _get_youtube_credentials()
    if not client_id:
        # Return a placeholder  
        return {"url": "", "error": "YOUTUBE_CLIENT_ID not set in environment"}
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": YOUTUBE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
    return {"url": f"https://accounts.google.com/o/oauth2/v2/auth?{params}"}


@router.get("/virality/youtube/oauth2callback")
def youtube_oauth2_callback(code: str = "", error: str = ""):
    from fastapi.responses import HTMLResponse
    if error:
        return HTMLResponse(f"<h1>OAuth Error</h1><p>{error}</p>")
    if not code:
        return HTMLResponse("<h1>Error</h1><p>No authorization code provided.</p>")

    # Exchange code for tokens
    client_id, client_secret = _get_youtube_credentials()
    token_url = "https://oauth2.googleapis.com/token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": _REDIRECT_URI
    }).encode("utf-8")

    try:
        req = urllib.request.Request(token_url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_info = json.loads(resp.read())
            
        access_token = token_info.get("access_token", "")
        refresh_token = token_info.get("refresh_token", "")
        
        # Now fetch the user's channel to get their ID and name
        channel_id = ""
        channel_name = ""
        try:
            me = _yt_api_get("/channels", {"mine": "true", "part": "id,snippet"}, access_token)
            items = me.get("items", [])
            if items:
                channel_id = items[0]["id"]
                channel_name = items[0]["snippet"]["title"]
        except Exception as e:
            print(f"[Virality] Warning: could not fetch channel info during OAuth: {e}")

        with _db() as conn:
            conn.execute("""
                UPDATE connections SET
                    access_token=?, refresh_token=?, channel_id=?,
                    channel_name=?, connected=1
                WHERE platform='youtube'
            """, (access_token, refresh_token, channel_id, channel_name))

        return HTMLResponse("""
            <html>
                <head><title>Success</title></head>
                <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                    <h2>YouTube Connected Successfully!</h2>
                    <p>You can close this window and return to the Fade editor.</p>
                    <script>
                        setTimeout(() => window.close(), 1500);
                    </script>
                </body>
            </html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h1>Token Exchange Failed</h1><p>{e}</p>")


@router.post("/virality/connections/youtube")
def connect_youtube(req: YTTokens):
    with _db() as conn:
        conn.execute("""
            UPDATE connections SET
                access_token=?, refresh_token=?, channel_id=?,
                channel_name=?, expires_at=?, connected=1
            WHERE platform='youtube'
        """, (req.access_token, req.refresh_token, req.channel_id,
              req.channel_name, req.expires_at))
    return {"ok": True}


@router.delete("/virality/connections/youtube")
def disconnect_youtube():
    with _db() as conn:
        conn.execute("""
            UPDATE connections SET access_token='', refresh_token='',
            channel_id='', channel_name='', connected=0
            WHERE platform='youtube'
        """)
    return {"ok": True}


@router.post("/virality/connections/instagram")
def connect_instagram(req: IGTokens):
    with _db() as conn:
        conn.execute("""
            UPDATE connections SET access_token=?, channel_id=?,
            channel_name=?, connected=1
            WHERE platform='instagram'
        """, (req.access_token, req.user_id, req.username))
    return {"ok": True}


@router.delete("/virality/connections/instagram")
def disconnect_instagram():
    with _db() as conn:
        conn.execute("""
            UPDATE connections SET access_token='', channel_id='',
            channel_name='', connected=0 WHERE platform='instagram'
        """)
    return {"ok": True}



# YouTube quick-connect  

class YTQuickConnect(BaseModel):
    api_key:    str
    channel_id: str  # e.g. "UCxxxxxx" or "@handle"


@router.post("/virality/youtube/quick-connect")
def youtube_quick_connect(req: YTQuickConnect):
    """
    Simple path: user has a YouTube Data API key + their channel ID.
    We store the API key as the access_token and mark connected=1.
    No OAuth redirect needed.
    """
    global _YT_API_KEY
    _YT_API_KEY = req.api_key

    # Resolve channel info
    try:
        channel_id = req.channel_id.strip()
        params: dict = {"part": "id,snippet,statistics"}
        if channel_id.startswith("@"):
            params["forHandle"] = channel_id
        elif channel_id.startswith("UC"):
            params["id"] = channel_id
        else:
            params["forHandle"] = channel_id

        data = _yt_api_get("/channels", params, access_token="")
        items = data.get("items", [])
        if not items:
            raise HTTPException(404, f"Channel not found: {channel_id}")

        ch = items[0]
        resolved_id   = ch["id"]
        resolved_name = ch["snippet"]["title"]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Could not resolve channel: {exc}")

    with _db() as conn:
        conn.execute("""
            UPDATE connections SET
                access_token=?, channel_id=?, channel_name=?, connected=1
            WHERE platform='youtube'
        """, (req.api_key, resolved_id, resolved_name))

    return {"ok": True, "channel_id": resolved_id, "channel_name": resolved_name}


#   YouTube video listing  

@router.get("/virality/youtube/videos")
def get_youtube_videos():
    with _db() as conn:
        row = conn.execute("SELECT * FROM connections WHERE platform='youtube'").fetchone()

    if not row or not row["connected"]:
        raise HTTPException(400, "YouTube not connected")

    access_token  = row["access_token"]
    refresh_token = row["refresh_token"]
    channel_id    = row["channel_id"]

    # Auto-refresh: try the stored token; if it's a 401 use refresh_token to get a new one
    def _get_token_with_refresh() -> str:
        nonlocal access_token
        try:
            # Quick probe — just ask for the channel to validate the token
            _yt_api_get("/channels", {"mine": "true", "part": "id"}, access_token)
            return access_token
        except HTTPException as e:
            if e.status_code == 403 and "401" in str(e.detail):
                new_token = _refresh_yt_access_token(refresh_token)
                if new_token:
                    access_token = new_token
                    return access_token
            raise

    try:
        access_token = _get_token_with_refresh()
    except HTTPException:
        # Token expired and refresh failed — mark disconnected so UI shows reconnect button
        with _db() as conn:
            conn.execute("UPDATE connections SET connected=0 WHERE platform='youtube'")
        raise HTTPException(401, "YouTube session expired. Please reconnect in Settings.")

    if not channel_id:
        # Try to fetch it from the API
        try:
            me = _yt_api_get("/channels", {"mine": "true", "part": "id,snippet"}, access_token)
            items = me.get("items", [])
            if items:
                channel_id = items[0]["id"]
                ch_name = items[0]["snippet"]["title"]
                with _db() as conn:
                    conn.execute("UPDATE connections SET channel_id=?, channel_name=? WHERE platform='youtube'",
                                 (channel_id, ch_name))
        except Exception as exc:
            raise HTTPException(500, f"Could not fetch channel info: {exc}")

    videos = _fetch_latest_yt_videos(channel_id, access_token)
    # Map numeric category IDs
    for v in videos:
        v["category"] = _map_yt_category(v["category"])
    return {"videos": videos}


#   Analyze endpoint  

@router.post("/virality/analyze")
def analyze_video(req: AnalyzeRequest):
    pipeline = _get_pipeline()
    if pipeline is None:
        raise HTTPException(503, "Virality model not loaded. Check that AIModels/SIH_Virality_Prototype/models/ has all .pkl files.")

  
    thumb_bytes = _fetch_yt_thumbnail_bytes(req.thumbUrl) if req.thumbUrl else b""
    if not thumb_bytes:
        raise HTTPException(400, "Could not fetch thumbnail image")

    try:
        from PIL import Image as _PIL_Image
        img = _PIL_Image.open(BytesIO(thumb_bytes)).convert("RGB")
    except Exception as exc:
        raise HTTPException(400, f"Could not decode thumbnail: {exc}")

    
    model_cat = req.category if req.category in _MODEL_CATEGORIES else "Entertainment"

 
    try:
        scores = pipeline.predict(
            image_pil=img,
            text=req.title,
            platform=req.platform.lower(),
            category=model_cat,
            baseline_views=req.baselineViews,
        )
    except Exception as exc:
        raise HTTPException(500, f"Model inference error: {exc}")

    q_score = int(scores["quality_score"] * 100)
    t_score = int(scores["text_score"]    * 100)
    v_score = int(scores["virality_score"] * 100)

    # 4. Build LLM prompt
    prompt = f"""You are an expert YouTube content strategist and virality analyst.

A creator's video has been analyzed by a two-stage AI model. Here are the results:

**Video Title:** {req.title}
**Platform:** {req.platform.title()}
**Category:** {model_cat}
**Creator Baseline Views (median):** {req.baselineViews:,}

**AI Model Scores (0-100):**
- Creative Quality (Visual/Thumbnail): {q_score}/100
- Title/Text Semantic Strength: {t_score}/100
- Virality Potential (Stage 2): {v_score}/100

**Context:** The model uses ResNet-18 for visual aesthetics (Stage 1, ~0.68 AUC) and a meta-model combining visual, text, and context features for virality (Stage 2, ~0.53 AUC). Algorithmic virality also depends on timing, promotion, and unobservable momentum.

**Your Task:**
1. Give a concise 2-3 sentence overall assessment.
2. List 3 specific, actionable improvements the creator can make RIGHT NOW.
3. Rate the chances of this outperforming their baseline (Low/Medium/High) and explain why.
4. Add a one-line "Creator Pro Tip" at the end.

Be direct, insightful, and encouraging. Format with markdown headers."""

 
    try:
        llm_response = _call_llm(prompt)
    except Exception as exc:
    
        try:
            _reco_src = str(_PIPELINE_SRC)
            if _reco_src not in sys.path:
                sys.path.insert(0, _reco_src)
            from recommendations import generate_recommendation  # type: ignore
            llm_response = generate_recommendation(scores, req.baselineViews)
        except Exception:
            llm_response = (
                f"## Analysis\n\n"
                f"**Creative Quality:** {q_score}/100\n\n"
                f"**Title Strength:** {t_score}/100\n\n"
                f"**Virality Potential:** {v_score}/100\n\n"
                f"_(LLM not configured — showing raw model scores. "
                f"Set OPENAI_API_KEY to enable AI narrative analysis.)_"
            )

    return {
        "scores": {
            "quality":  q_score,
            "text":     t_score,
            "virality": v_score,
        },
        "analysis": llm_response,
        "prompt":   prompt,
    }
