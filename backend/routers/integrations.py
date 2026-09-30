 
from __future__ import annotations

import os
import json
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Shared DB  

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


def _ensure_provider_rows() -> None:
    """Guarantee that rows for all four providers exist in the connections table.
    This is idempotent; virality.py already seeds youtube and instagram."""
    with _db() as conn:
 
        try:
            conn.execute(
                "ALTER TABLE connections ADD COLUMN connected_at TEXT DEFAULT ''"
            )
        except sqlite3.OperationalError:
            pass  # Column already exists — that is fine.

        for platform in ("youtube", "instagram", "linkedin", "gmail"):
            conn.execute(
                "INSERT OR IGNORE INTO connections (platform) VALUES (?)",
                (platform,),
            )


_ensure_provider_rows()


#   Environment helpers  

def _env(key: str, default: str = "") -> str:
    """Read an env variable, reloading .env on each call is intentionally
    skipped for performance — .env is loaded once at startup by main.py."""
    return os.environ.get(key, default)


def _is_configured(provider: str) -> bool:
    """Return True if the minimum env vars for this provider are present."""
    checks: dict[str, list[str]] = {
        "youtube":   ["GOOGLE_CLIENT_ID",  "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"],
        "instagram": ["INSTAGRAM_APP_ID",   "INSTAGRAM_APP_SECRET"],
        "linkedin":  ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"],
        "gmail":     ["GMAIL_CLIENT_ID",    "GMAIL_CLIENT_SECRET"],
    }
    required = checks.get(provider, [])
    return all(_env(k) for k in required)


 

def _redirect_uri(provider: str) -> str:
    port = int(os.environ.get("BACKEND_PORT", 8000))
    return f"http://127.0.0.1:{port}/integrations/{provider}/callback"


#   Provider OAuth URL builders  

def _youtube_auth_url() -> str:
    params = urllib.parse.urlencode({
        "client_id": _env("GOOGLE_CLIENT_ID"),
        "redirect_uri": _env("GOOGLE_REDIRECT_URI"),
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube",
        "access_type": "offline",
        "prompt": "consent",
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"


def _gmail_auth_url() -> str:
    scopes = " ".join([
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ])
    params = urllib.parse.urlencode({
        "client_id": _env("GMAIL_CLIENT_ID"),
        "redirect_uri":  _redirect_uri("gmail"),
        "response_type": "code",
        "scope": scopes,
        "access_type":   "offline",
        "prompt": "consent",
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"


def _linkedin_auth_url() -> str:
    scopes = "openid profile email w_member_social"
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": _env("LINKEDIN_CLIENT_ID"),
        "redirect_uri": _redirect_uri("linkedin"),
        "scope": scopes,
        "state": "fade-linkedin-oauth",
    })
    return f"https://www.linkedin.com/oauth/v2/authorization?{params}"


def _instagram_auth_url() -> str:
    """
    Instagram Business Login.
    Requires a Meta App with Instagram Business Login configured.
    """
    scopes = "instagram_business_basic,instagram_business_content_publish"
    params = urllib.parse.urlencode({
        "client_id": _env("INSTAGRAM_APP_ID"),
        "redirect_uri": _env("INSTAGRAM_REDIRECT_URI", _redirect_uri("instagram")),
        "scope": scopes,
        "response_type": "code",
    })
    return f"https://www.instagram.com/oauth/authorize?{params}"


_AUTH_URL_BUILDERS = {
    "youtube": _youtube_auth_url,
    "gmail": _gmail_auth_url,
    "linkedin": _linkedin_auth_url,
    "instagram": _instagram_auth_url,
}


# Token exchange helpers  

def _post_form(url: str, data: dict) -> dict:
    """POST application/x-www-form-urlencoded and return JSON response."""
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=encoded, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _api_get(url: str, access_token: str) -> dict:
    """GET JSON with Bearer token."""
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _exchange_youtube(code: str) -> dict:
    """Exchange code, return {access_token, refresh_token, channel_id, channel_name}."""
    token_data = _post_form("https://oauth2.googleapis.com/token", {
        "code": code,
        "client_id": _env("GOOGLE_CLIENT_ID"),
        "client_secret": _env("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": _env("GOOGLE_REDIRECT_URI"),
        "grant_type": "authorization_code",
    })
    access_token  = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    # Fetch channel name
    channel_id, channel_name = "", ""
    try:
        yt = _api_get(
            "https://www.googleapis.com/youtube/v3/channels"
            "?mine=true&part=id,snippet",
            access_token,
        )
        items = yt.get("items", [])
        if items:
            channel_id   = items[0]["id"]
            channel_name = items[0]["snippet"]["title"]
    except Exception as exc:
        print(f"[Integrations] YouTube channel fetch warning: {exc}", flush=True)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "channel_id": channel_id,
        "channel_name": channel_name,
    }


def _exchange_gmail(code: str) -> dict:
    """Exchange code, return {access_token, refresh_token, channel_name (email)}."""
    token_data = _post_form("https://oauth2.googleapis.com/token", {
        "code":          code,
        "client_id": _env("GMAIL_CLIENT_ID"),
        "client_secret": _env("GMAIL_CLIENT_SECRET"),
        "redirect_uri":  _redirect_uri("gmail"),
        "grant_type":    "authorization_code",
    })
    access_token  = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    # Fetch user email
    account_email = ""
    try:
        userinfo = _api_get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            access_token,
        )
        account_email = userinfo.get("email", "")
    except Exception as exc:
        print(f"[Integrations] Gmail userinfo warning: {exc}", flush=True)

    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "channel_id": account_email,   # reuse channel_id col for email
        "channel_name":  account_email,
    }


def _exchange_linkedin(code: str) -> dict:
    """Exchange code, return {access_token, channel_name (full name)}."""
    token_data = _post_form(
        "https://www.linkedin.com/oauth/v2/accessToken",
        {
            "code": code,
            "client_id": _env("LINKEDIN_CLIENT_ID"),
            "client_secret": _env("LINKEDIN_CLIENT_SECRET"),
            "redirect_uri": _redirect_uri("linkedin"),
            "grant_type": "authorization_code",
        },
    )
    access_token = token_data.get("access_token", "")

    # LinkedIn OpenID Connect userinfo
    display_name = ""
    try:
        profile = _api_get(
            "https://api.linkedin.com/v2/userinfo",
            access_token,
        )
        display_name = profile.get("name", "") or (
            f"{profile.get('given_name','')} {profile.get('family_name','')}".strip()
        )
    except Exception as exc:
        print(f"[Integrations] LinkedIn userinfo warning: {exc}", flush=True)

    return {
        "access_token":  access_token,
        "refresh_token": "",          # LinkedIn short-lived tokens; no refresh
        "channel_id": display_name,
        "channel_name": display_name,
    }


def _exchange_instagram(code: str) -> dict:
    """Exchange code for a short-lived token, then upgrade to long-lived."""
    # Step 1: short-lived token
    code = code.rstrip("#_")
    short_data = _post_form(
        "https://api.instagram.com/oauth/access_token",
        {
            "client_id": _env("INSTAGRAM_APP_ID"),
            "client_secret": _env("INSTAGRAM_APP_SECRET"),
            "grant_type": "authorization_code",
            "redirect_uri":  _env("INSTAGRAM_REDIRECT_URI", _redirect_uri("instagram")),
            "code": code,
        },
    )
    short_token = short_data.get("access_token", "")
    user_id     = str(short_data.get("user_id", ""))

    #   exchange for long-lived token 
    long_token = short_token
    try:
        params = urllib.parse.urlencode({
            "grant_type": "ig_exchange_token",
            "client_secret": _env("INSTAGRAM_APP_SECRET"),
            "access_token": short_token,
        })
        req = urllib.request.Request(
            f"https://graph.instagram.com/access_token?{params}"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            long_data = json.loads(resp.read())
        long_token = long_data.get("access_token", short_token)
    except Exception as exc:
        print(f"[Integrations] Instagram long-lived token upgrade warning: {exc}",
              flush=True)

    # Fetch username
    username = user_id
    try:
        me = _api_get(
            f"https://graph.instagram.com/me?fields=id,username&access_token={long_token}",
            long_token,
        )
        username = me.get("username", user_id)
    except Exception as exc:
        print(f"[Integrations] Instagram username fetch warning: {exc}", flush=True)

    return {
        "access_token":  long_token,
        "refresh_token": "",
        "channel_id": user_id,
        "channel_name":  username,
    }


_TOKEN_EXCHANGERS = {
    "youtube": _exchange_youtube,
    "gmail": _exchange_gmail,
    "linkedin": _exchange_linkedin,
    "instagram": _exchange_instagram,
}


#   DB helpers  

def _store_connection(provider: str, tokens: dict) -> None:
    """Persist tokens to DB. Never logs token values."""
    print(
        f"[Integrations] Storing {provider} connection "
        f"(account={tokens.get('channel_name', '?')!r}, "
        f"token_len={len(tokens.get('access_token',''))})",
        flush=True,
    )
    connected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _db() as conn:
        conn.execute(
            """
            UPDATE connections
            SET access_token=?, refresh_token=?, channel_id=?,
                channel_name=?, connected=1, connected_at=?
            WHERE platform=?
            """,
            (
                tokens["access_token"],
                tokens.get("refresh_token", ""),
                tokens.get("channel_id", ""),
                tokens.get("channel_name", ""),
                connected_at,
                provider,
            ),
        )


def _clear_connection(provider: str) -> None:
    with _db() as conn:
        conn.execute(
            """
            UPDATE connections
            SET access_token='', refresh_token='', channel_id='',
                channel_name='', connected=0, connected_at=''
            WHERE platform=?
            """,
            (provider,),
        )


def _get_safe_status(provider: str) -> dict:
    """Return connection metadata WITHOUT any token data."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM connections WHERE platform=?", (provider,)
        ).fetchone()

    if row is None:
        return {
            "provider": provider,
            "connected":   False,
            "configured":  _is_configured(provider),
            "accountName": None,
            "connectedAt": None,
        }

    return {
        "provider":    provider,
        "connected":   bool(row["connected"]),
        "configured":  _is_configured(provider),
        "accountName": row["channel_name"] or None,
        "connectedAt": row["connected_at"] if "connected_at" in row.keys() else None,
    }


#   HTML response pages  

_SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Connected — FADE</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      min-height: 100vh; display: flex; align-items: center;
      justify-content: center; flex-direction: column; gap: 16px;
      background: #0d0d12; font-family: 'Inter', system-ui, sans-serif;
      color: #e0e0e6;
    }}
    .icon {{ font-size: 56px; }}
    h2 {{ font-size: 22px; font-weight: 600; color: #00d4aa; }}
    p  {{ font-size: 14px; color: rgba(255,255,255,0.45); }}
  </style>
</head>
<body>
  <div class="icon">✅</div>
  <h2>{provider_label} Connected!</h2>
  <p>You can close this window and return to FADE.</p>
  <script>setTimeout(() => window.close(), 2000);</script>
</body>
</html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Connection Error — FADE</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      min-height: 100vh; display: flex; align-items: center;
      justify-content: center; flex-direction: column; gap: 16px;
      background: #0d0d12; font-family: 'Inter', system-ui, sans-serif;
      color: #e0e0e6;
    }}
    .icon {{ font-size: 56px; }}
    h2 {{ font-size: 22px; font-weight: 600; color: #ff6b6b; }}
    p  {{ font-size: 14px; color: rgba(255,255,255,0.45); }}
    .reason {{ font-size: 13px; color: #ff9999; margin-top: 4px; }}
  </style>
</head>
<body>
  <div class="icon">❌</div>
  <h2>Connection Failed</h2>
  <p>{safe_message}</p>
  <p class="reason">{safe_reason}</p>
  <p style="margin-top:12px">You can close this window.</p>
</body>
</html>"""

_PROVIDER_LABELS = {
    "youtube":   "YouTube",
    "instagram": "Instagram",
    "linkedin":  "LinkedIn",
    "gmail":     "Gmail",
}


#   Routes  

@router.get("")
def list_connections():
    """
    GET /integrations
    Returns safe metadata for all providers. No tokens are included.
    """
    providers = ["youtube", "instagram", "linkedin", "gmail"]
    return [_get_safe_status(p) for p in providers]


@router.get("/{provider}/connect")
def get_connect_url(provider: str):
    """
    GET /integrations/{provider}/connect
    Returns the OAuth authorization URL for the given provider.
    The Electron frontend opens this URL in the system browser.
    """
    if provider not in _AUTH_URL_BUILDERS:
        raise HTTPException(404, f"Unknown provider: {provider!r}")

    if not _is_configured(provider):
        raise HTTPException(
            400,
            f"{_PROVIDER_LABELS.get(provider, provider)} credentials are not configured. "
            f"Add the required keys to your .env file.",
        )

    url = _AUTH_URL_BUILDERS[provider]()
    return {"provider": provider, "url": url}


@router.get("/{provider}/callback")
def oauth_callback(provider: str, code: str = "", error: str = "",
                   error_description: str = ""):
    """
    GET /integrations/{provider}/callback?code=...
    Receives the OAuth authorization code, exchanges it for tokens,
    stores them securely, and returns a user-facing HTML page.
    The user's browser lands here after authorizing in the system browser.
    """
    label = _PROVIDER_LABELS.get(provider, provider.title())

    if error:
        # User cancelled or provider returned an error — safe to show to user
        safe_reason = "Authorization was cancelled or denied."
        if error == "access_denied":
            safe_reason = "Authorization was cancelled."
        return HTMLResponse(
            _ERROR_HTML.format(
                safe_message=f"Could not connect {label}.",
                safe_reason=safe_reason,
            )
        )

    if not code:
        return HTMLResponse(
            _ERROR_HTML.format(
                safe_message=f"Could not connect {label}.",
                safe_reason="No authorization code was returned by the provider.",
            )
        )

    if provider not in _TOKEN_EXCHANGERS:
        return HTMLResponse(
            _ERROR_HTML.format(
                safe_message=f"Unknown provider: {label}.",
                safe_reason="",
            )
        )

    try:
        tokens = _TOKEN_EXCHANGERS[provider](code)
        _store_connection(provider, tokens)
    except urllib.error.HTTPError as exc:
        # Do NOT include any token data or secret in the message shown to the user.
        print(f"[Integrations] {provider} callback HTTP error: {exc}", flush=True)
        return HTMLResponse(
            _ERROR_HTML.format(
                safe_message=f"Failed to connect {label}.",
                safe_reason="The provider returned an error during token exchange. "
                            "Please try again.",
            )
        )
    except Exception as exc:
        print(f"[Integrations] {provider} callback error: {exc}", flush=True)
        return HTMLResponse(
            _ERROR_HTML.format(
                safe_message=f"Failed to connect {label}.",
                safe_reason="An unexpected error occurred. Please try again.",
            )
        )

    return HTMLResponse(
        _SUCCESS_HTML.format(provider_label=label)
    )


@router.post("/{provider}/disconnect")
def disconnect_provider(provider: str):
    """
    POST /integrations/{provider}/disconnect
    Clears stored credentials and marks the provider as disconnected.
    Handles the case where credentials were already revoked externally.
    """
    if provider not in _AUTH_URL_BUILDERS:
        raise HTTPException(404, f"Unknown provider: {provider!r}")

    _clear_connection(provider)
    print(f"[Integrations] {provider} disconnected.", flush=True)
    return {"ok": True, "provider": provider}


@router.get("/{provider}/status")
def provider_status(provider: str):
    """
    GET /integrations/{provider}/status
    Returns the safe status for a single provider.
    """
    if provider not in _AUTH_URL_BUILDERS:
        raise HTTPException(404, f"Unknown provider: {provider!r}")
    return _get_safe_status(provider)
