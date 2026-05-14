from __future__ import annotations

import logging
import os
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

INDEXNOW_NAVER_URL = "https://searchadvisor.naver.com/indexnow"


def _get_indexnow_key() -> str:
    return os.getenv("INDEXNOW_KEY", "").strip()


def submit_to_naver_indexnow(post_url: str, domain: str = "") -> str:
    """네이버 서치어드바이저 IndexNow API로 수집요청.

    Returns:
        결과 문자열 ("200", "202", "error:...", "skipped" 등)
    """
    key = _get_indexnow_key()
    if not key:
        return "skipped:no_indexnow_key"

    if not domain:
        # post_url에서 도메인 추출
        from urllib.parse import urlparse
        parsed = urlparse(post_url)
        domain = parsed.netloc or parsed.hostname or ""

    if not domain:
        return "skipped:no_domain"

    payload = {
        "host": domain,
        "key": key,
        "keyLocation": f"https://{domain}/{key}.txt",
        "urlList": [post_url],
    }

    try:
        resp = requests.post(
            INDEXNOW_NAVER_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        status = resp.status_code
        if status in (200, 202):
            logger.info("Naver IndexNow OK (%s): %s", status, post_url)
            return str(status)
        else:
            logger.warning("Naver IndexNow %s: %s — %s", status, post_url, resp.text[:200])
            return f"http_{status}"
    except (requests.Timeout, requests.ConnectionError, requests.RequestException) as exc:
        logger.warning("Naver IndexNow failed for %s: %s", post_url, exc)
        return f"error:{type(exc).__name__}"


def submit_post_to_search_sites(post_url: str, sitemap_url: str = "", domain: str = "") -> dict[str, str]:
    """Google/Bing sitemap ping + 네이버 IndexNow 수집요청."""
    result = {
        "google": "skipped",
        "bing": "skipped",
        "naver": "skipped",
    }

    # 네이버 IndexNow
    result["naver"] = submit_to_naver_indexnow(post_url, domain=domain)

    if not sitemap_url:
        return result

    # Google sitemap ping
    google_ping = f"https://www.google.com/ping?sitemap={quote_plus(sitemap_url)}"
    try:
        g = requests.get(google_ping, timeout=15)
        result["google"] = str(g.status_code) if 200 <= g.status_code < 300 else f"http_{g.status_code}"
    except (requests.Timeout, requests.ConnectionError, requests.RequestException) as exc:
        logger.warning("Google ping failed for sitemap %s: %s", sitemap_url, exc)
        result["google"] = f"error:{type(exc).__name__}"

    # Bing sitemap ping
    bing_ping = f"https://www.bing.com/ping?sitemap={quote_plus(sitemap_url)}"
    try:
        b = requests.get(bing_ping, timeout=15)
        result["bing"] = str(b.status_code) if 200 <= b.status_code < 300 else f"http_{b.status_code}"
    except (requests.Timeout, requests.ConnectionError, requests.RequestException) as exc:
        logger.warning("Bing ping failed for sitemap %s: %s", sitemap_url, exc)
        result["bing"] = f"error:{type(exc).__name__}"

    return result
