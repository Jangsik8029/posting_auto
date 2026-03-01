from __future__ import annotations

from urllib.parse import quote_plus

import requests


def submit_post_to_search_sites(post_url: str, sitemap_url: str = "") -> dict[str, str]:
    """
    Practical baseline:
    - If sitemap_url is provided, ping Google/Bing sitemap endpoints.
    - Naver Search Advisor has no simple public ping endpoint; mark as manual.
    """
    _ = post_url
    result = {
        "google": "skipped",
        "bing": "skipped",
        "naver": "manual_required",
    }

    if not sitemap_url:
        return result

    google_ping = f"https://www.google.com/ping?sitemap={quote_plus(sitemap_url)}"
    bing_ping = f"https://www.bing.com/ping?sitemap={quote_plus(sitemap_url)}"

    try:
        g = requests.get(google_ping, timeout=15)
        result["google"] = str(g.status_code)
    except Exception as exc:
        result["google"] = f"error:{exc}"

    try:
        b = requests.get(bing_ping, timeout=15)
        result["bing"] = str(b.status_code)
    except Exception as exc:
        result["bing"] = f"error:{exc}"

    return result

