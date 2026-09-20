from __future__ import annotations

import time
import random
from dataclasses import dataclass


@dataclass
class NewsItem:
    title: str
    body: str
    url: str
    source: str = ""


def _get_ddgs():
    """Return a DDGS instance, preferring the new `ddgs` package."""
    try:
        from ddgs import DDGS
        return DDGS()
    except ImportError:
        pass
    # Suppress the deprecation RuntimeWarning from the old package
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        from duckduckgo_search import DDGS  # type: ignore
    return DDGS()


def _ddgs_news(ddgs, query: str, max_results: int) -> list[dict]:
    """Try news search; returns [] on any error."""
    try:
        return list(ddgs.news(query, max_results=max_results))
    except TypeError:
        # Old API signature
        return list(ddgs.news(
            keywords=query,
            region="wt-wt",
            safesearch="moderate",
            max_results=max_results,
        ))


def _ddgs_text(ddgs, query: str, max_results: int) -> list[dict]:
    """Fallback: web text search when news search is unavailable."""
    try:
        raw = list(ddgs.text(query, max_results=max_results))
        # Normalise to news-item shape
        return [
            {
                "title": r.get("title", ""),
                "body": r.get("body", r.get("snippet", "")),
                "url": r.get("href", r.get("url", "")),
                "source": r.get("source", "web"),
            }
            for r in raw
        ]
    except Exception:
        return []


def search_news(query: str, max_results: int = 10) -> list["NewsItem"]:
    print(f"[NewsSearch] Searching for: {query!r}", flush=True)

    MAX_ATTEMPTS = 3
    for attempt in range(MAX_ATTEMPTS):
        try:
            ddgs = _get_ddgs()
            results = _ddgs_news(ddgs, query, max_results)

            if not results:
                # News endpoint empty or rate-limited — try text search
                print("[NewsSearch] News search empty, trying text search...", flush=True)
                results = _ddgs_text(ddgs, query, max_results)

            items = [
                NewsItem(
                    title=r.get("title", ""),
                    body=r.get("body", r.get("excerpt", "")),
                    url=r.get("url", r.get("href", "")),
                    source=r.get("source", ""),
                )
                for r in results
            ]
            print(f"[NewsSearch] Found {len(items)} articles", flush=True)
            return items

        except Exception as e:
            err = str(e)
            is_ratelimit = "403" in err or "Ratelimit" in err or "ratelimit" in err.lower()
            if is_ratelimit and attempt < MAX_ATTEMPTS - 1:
                wait = random.uniform(3, 6) * (2 ** attempt)  # 3-6s, 6-12s
                print(
                    f"[NewsSearch] Rate-limited (attempt {attempt + 1}/{MAX_ATTEMPTS}), "
                    f"retrying in {wait:.1f}s...",
                    flush=True,
                )
                time.sleep(wait)
                continue
            print(f"[NewsSearch] Search failed: {e}", flush=True)
            return []

    return []


def format_for_llm(items: list["NewsItem"]) -> str:
    """Formats news items into a compact string for the LLM prompt."""
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. [{item.source}] {item.title}")
        if item.body:
            lines.append(f"   {item.body[:200].strip()}")
    return "\n".join(lines)
