import html
import os
import re
from typing import Iterator

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cafe_crawler.config import (
    NAVER_DISPLAY,
    NAVER_MAX_PAGES,
    REQUEST_TIMEOUT,
)

API_URL = "https://openapi.naver.com/v1/search/cafearticle.json"
TAG_RE = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    return html.unescape(TAG_RE.sub("", text or "")).strip()


def _keys() -> tuple[str, str]:
    cid = os.getenv("NAVER_CLIENT_ID", "")
    csec = os.getenv("NAVER_CLIENT_SECRET", "")
    if not cid or not csec:
        raise RuntimeError(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 .env 에 설정되어야 합니다."
        )
    return cid, csec


class NaverApiError(RuntimeError):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((requests.RequestException, NaverApiError)),
)
def _call(query: str, display: int, start: int, sort: str) -> dict:
    cid, csec = _keys()
    headers = {
        "X-Naver-Client-Id": cid,
        "X-Naver-Client-Secret": csec,
    }
    params = {"query": query, "display": display, "start": start, "sort": sort}
    resp = requests.get(API_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 401:
        raise RuntimeError("네이버 API 인증 실패 (401). Client ID/Secret 확인 필요.")
    if resp.status_code >= 500:
        raise NaverApiError(f"naver 5xx: {resp.status_code}")
    if resp.status_code != 200:
        raise NaverApiError(f"naver {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def search_naver_cafe(
    query: str,
    display: int = NAVER_DISPLAY,
    max_pages: int = NAVER_MAX_PAGES,
    sort: str = "sim",
) -> Iterator[dict]:
    """네이버 카페글 검색. 페이지네이션 한계: start <= 1000."""
    rank = 0
    for page in range(max_pages):
        start = page * display + 1
        if start > 1000:
            break
        data = _call(query, display, start, sort)
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            rank += 1
            yield {
                "platform": "naver",
                "title": _strip(item.get("title", "")),
                "url": item.get("link", ""),
                "snippet": _strip(item.get("description", "")),
                "cafe_name": item.get("cafename", ""),
                "cafe_url": item.get("cafeurl", ""),
                "posted_at": None,
                "rank": rank,
            }
        if len(items) < display:
            break
