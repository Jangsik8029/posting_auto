from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, quote_plus, urlparse

import requests
import xml.etree.ElementTree as ET

from blogbot.clients.http import TIMEOUT_DEFAULT, get_shared_session

logger = logging.getLogger(__name__)


def _clean_ddg_redirect(url: str) -> str:
    if "duckduckgo.com/l/?" not in url:
        return url
    qs = parse_qs(urlparse(url).query)
    return qs.get("uddg", [url])[0]


def collect_reference_material(main_topic: str, sub_topics: list[str], max_links: int = 5) -> list[dict[str, str]]:
    query = " ".join([main_topic, *sub_topics]).strip()
    if not query:
        return []

    session = get_shared_session()
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        response = session.get(search_url, timeout=TIMEOUT_DEFAULT)
    except requests.RequestException as exc:
        logger.warning("DuckDuckGo search failed for %r: %s", query, exc)
        response = None
    refs: list[dict[str, str]] = []
    if response is not None and response.status_code == 200:
        html = response.text
        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        seen: set[str] = set()
        for raw_url, raw_title in pattern.findall(html):
            url = _clean_ddg_redirect(raw_url.strip())
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            if not url or not title or url in seen:
                continue
            seen.add(url)
            refs.append({"title": title, "url": url})
            if len(refs) >= max_links:
                return refs

    # Fallback: Bing RSS
    rss_url = f"https://www.bing.com/search?q={quote_plus(query)}&format=rss"
    try:
        rss_resp = session.get(rss_url, timeout=TIMEOUT_DEFAULT)
    except requests.RequestException as exc:
        logger.warning("Bing RSS fetch failed for %r: %s", query, exc)
        return refs
    if rss_resp.status_code != 200:
        logger.info("Bing RSS returned HTTP %s for %r", rss_resp.status_code, query)
        return refs
    try:
        root = ET.fromstring(rss_resp.text)
    except ET.ParseError as exc:
        logger.warning("Bing RSS parse failed for query %r: %s", query, exc)
        return refs

    seen = {x["url"] for x in refs}
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url or url in seen:
            continue
        refs.append({"title": title, "url": url})
        seen.add(url)
        if len(refs) >= max_links:
            break
    return refs
