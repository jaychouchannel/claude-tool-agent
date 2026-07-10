"""Web search tool using DuckDuckGo HTML endpoint (no API key needed)."""
import urllib.parse
import urllib.request
import re

from bs4 import BeautifulSoup

DDG_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

TOOL_SPEC = {
    "name": "web_search",
    "description": "Search the web using DuckDuckGo and return the top results. Use for current events, recent news, or facts you don't know.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}


def run(query: str, max_results: int = 5) -> str:
    """Execute the search and return formatted results."""
    try:
        params = urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(
            f"{DDG_URL}?{params}",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return f"Search failed: {e}"

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select(".result")[:max_results]:
        title_el = item.select_one(".result__a")
        snippet_el = item.select_one(".result__snippet")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        # DDG wraps URLs in a redirect
        m = re.search(r"uddg=([^&]+)", href)
        url = urllib.parse.unquote(m.group(1)) if m else href
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        results.append(f"**{title}**\n{url}\n{snippet}")

    if not results:
        return f"No results found for: {query}"

    return "\n\n".join(results)
