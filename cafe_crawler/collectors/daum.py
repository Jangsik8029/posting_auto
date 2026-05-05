import html
import os
import re
from typing import Iterator

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cafe_crawler.config import (
    KAKAO_MAX_PAGES,
    KAKAO_SIZE,
    REQUEST_TIMEOUT,
)

API_URL = "https://dapi.kakao.com/v2/search/cafe"
TAG_RE = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    return html.unescape(TAG_RE.sub("", text or "")).strip()


def _key() -> str:
    k = os.getenv("KAKAO_REST_API_KEY", "")
    if not k:
        raise RuntimeError("KAKAO_REST_API_KEY 가 .env 에 설정되어야 합니다.")
    return k


class KakaoApiError(RuntimeError):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((requests.RequestException, KakaoApiError)),
)
def _call(query: str, size: int, page: int, sort: str) -> dict:
    headers = {"Authorization": f"KakaoAK {_key()}"}
    params = {"query": query, "size": size, "page": page, "sort": sort}
    resp = requests.get(API_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 401:
        raise RuntimeError("카카오 API 인증 실패 (401). REST API 키 확인 필요.")
    if resp.status_code >= 500:
        raise KakaoApiError(f"kakao 5xx: {resp.status_code}")
    if resp.status_code != 200:
        raise KakaoApiError(f"kakao {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def search_daum_cafe(
    query: str,
    size: int = KAKAO_SIZE,
    max_pages: int = KAKAO_MAX_PAGES,
    sort: str = "accuracy",
) -> Iterator[dict]:
    """카카오 검색 API - 카페글. page 1..50, size 1..50."""
    rank = 0
    for page in range(1, max_pages + 1):
        if page > 50:
            break
        data = _call(query, size, page, sort)
        documents = data.get("documents", [])
        if not documents:
            break
        for doc in documents:
            rank += 1
            yield {
                "platform": "daum",
                "title": _strip(doc.get("title", "")),
                "url": doc.get("url", ""),
                "snippet": _strip(doc.get("contents", "")),
                "cafe_name": doc.get("cafename", ""),
                "cafe_url": doc.get("cafeurl", ""),
                "posted_at": doc.get("datetime"),
                "rank": rank,
            }
        meta = data.get("meta", {})
        if meta.get("is_end"):
            break
