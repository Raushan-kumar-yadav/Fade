 
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class NewsItem:
    title: str
    body: str
    url: str
    source: str = ""


def search_news(query: str, max_results: int = 10) -> list[NewsItem]:
     
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS  # fallback

    print(f"[NewsSearch] Searching for: {query!r}", flush=True)

    items: list[NewsItem] = []
    try:
        with DDGS() as ddgs:
            try:
                # New ddgs API 
                results = list(ddgs.news(query, max_results=max_results))
            except TypeError:
                # Old duckduckgo_search API 
                results = list(ddgs.news(
                    keywords=query,
                    region="wt-wt",
                    safesearch="moderate",
                    max_results=max_results,
                ))
    except Exception as e:
        print(f"[NewsSearch] Search failed: {e}", flush=True)
        results = []

    for r in results:
        items.append(NewsItem(
            title=r.get("title", ""),
            body=r.get("body", r.get("excerpt", "")),
            url=r.get("url", ""),
            source=r.get("source", ""),
        ))

    print(f"[NewsSearch] Found {len(items)} articles", flush=True)
    return items



def format_for_llm(items: list[NewsItem]) -> str:
    """Formats news items into a compact string for the LLM prompt."""
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. [{item.source}] {item.title}")
        if item.body:
            lines.append(f"   {item.body[:200].strip()}")
    return "\n".join(lines)
