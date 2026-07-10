"""Wikipedia search tool — pulls page summaries via the public REST summary API."""
import json
import urllib.parse
import urllib.request

SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
SEARCH_API = "https://en.wikipedia.org/w/rest.php/v1/search/title"
USER_AGENT = "claude-tool-agent-demo/1.0 (educational use)"

TOOL_SPEC = {
    "name": "wikipedia_search",
    "description": (
        "Search English Wikipedia and return a short summary of the best-matching page. "
        "Use for encyclopedic facts, biographies, geography, science, history, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look up on Wikipedia.",
            },
        },
        "required": ["query"],
    },
}


def _http_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def run(query: str) -> str:
    """Find the closest Wikipedia page and return its title, URL, and extract."""
    query = query.strip()
    if not query:
        return "Empty query."

    try:
        search_url = f"{SEARCH_API}?{urllib.parse.urlencode({'q': query, 'limit': 1})}"
        data = _http_json(search_url)
        pages = data.get("pages", [])
        if not pages:
            return f"No Wikipedia page found for: {query}"
        title = pages[0]["title"]
        summary_url = f"{SUMMARY_API}{urllib.parse.quote(title.replace(' ', '_'))}"
        summary = _http_json(summary_url)
    except Exception as e:
        return f"Wikipedia lookup failed: {e}"

    extract = summary.get("extract", "(no extract available)")
    page_url = summary.get("content_urls", {}).get("desktop", {}).get("page", "")
    title = summary.get("title", title)

    return f"**{title}**\n{page_url}\n\n{extract}"
