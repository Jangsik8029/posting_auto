from __future__ import annotations

import re
from urllib.parse import parse_qs, quote_plus, urlparse

import requests
import xml.etree.ElementTree as ET


def _clean_ddg_redirect(url: str) -> str:
    if "duckduckgo.com/l/?" not in url:
        return url
    qs = parse_qs(urlparse(url).query)
    return qs.get("uddg", [url])[0]


def collect_reference_material(main_topic: str, sub_topics: list[str], max_links: int = 5) -> list[dict[str, str]]:
    query = " ".join([main_topic, *sub_topics]).strip()
    if not query:
        return []

    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = requests.get(
        search_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    refs: list[dict[str, str]] = []
    if response.status_code == 200:
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
    rss_resp = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    if rss_resp.status_code != 200:
        return refs
    try:
        root = ET.fromstring(rss_resp.text)
    except ET.ParseError:
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
