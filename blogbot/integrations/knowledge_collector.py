from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlparse

import requests


@dataclass
class CollectedItem:
    source_url: str
    title: str
    body: str
    link: str


def _strip_html(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|li|tr|h1|h2|h3|h4|h5|h6)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_meta_description(html: str) -> str:
    m = re.search(
        r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )
    if not m:
        return ""
    return _strip_html(m.group(1))


def _extract_title(html: str, fallback: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not m:
        return fallback
    title = _strip_html(m.group(1))
    return title or fallback


def _normalize_same_host_url(base_url: str, raw_url: str) -> str:
    joined = urljoin(base_url, raw_url.strip())
    parsed = urlparse(joined)
    base_host = urlparse(base_url).netloc
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.netloc != base_host:
        return ""
    if parsed.query:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{parsed.query}"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _extract_links(base_url: str, html: str, max_links: int = 20) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    # Standard anchor href links
    for href in re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\']', html):
        clean = _normalize_same_host_url(base_url, href)
        if not clean:
            continue
        if clean in seen:
            continue
        seen.add(clean)
        links.append(clean)
        if len(links) >= max_links:
            break

    # JS inline paths often used in legacy sites (e.g. /nportal/...do)
    if len(links) < max_links:
        js_paths = re.findall(r'["\'](\/[^"\']+\.(?:do|jsp|html)(?:\?[^"\']*)?)["\']', html, re.IGNORECASE)
        for path in js_paths:
            clean = _normalize_same_host_url(base_url, path)
            if not clean or clean in seen:
                continue
            seen.add(clean)
            links.append(clean)
            if len(links) >= max_links:
                break
    return links


def _fetch(url: str, timeout: int = 20) -> tuple[str, str]:
    resp = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.5",
        },
    )
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "").lower()
    return resp.text, ctype


def collect_from_site(
    site_url: str,
    max_pages: int = 10,
    min_body_length: int = 20,
) -> list[CollectedItem]:
    html, ctype = _fetch(site_url)
    if "text/html" not in ctype and "<html" not in html.lower():
        return []

    home_title = _extract_title(html, fallback=site_url)
    home_body = _strip_html(html)
    if len(home_body) < min_body_length:
        meta_desc = _extract_meta_description(html)
        if meta_desc:
            home_body = f"{home_body} {meta_desc}".strip()
    items: list[CollectedItem] = []
    if home_body:
        items.append(CollectedItem(source_url=site_url, title=home_title, body=home_body, link=site_url))

    for link in _extract_links(site_url, html, max_links=max_pages):
        try:
            sub_html, sub_ctype = _fetch(link)
        except requests.RequestException:
            continue
        if "text/html" not in sub_ctype and "<html" not in sub_html.lower():
            continue
        title = _extract_title(sub_html, fallback=link)
        body = _strip_html(sub_html)
        if len(body) < min_body_length:
            meta_desc = _extract_meta_description(sub_html)
            if meta_desc:
                body = f"{body} {meta_desc}".strip()
        if len(body) < min_body_length:
            continue
        items.append(CollectedItem(source_url=site_url, title=title, body=body, link=link))
        if len(items) >= max_pages + 1:
            break
    return items
