"""네이버 DataLab 검색어트렌드 API를 활용한 인기 키워드 탐색."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cafe_crawler.config import REQUEST_TIMEOUT

API_URL = "https://openapi.naver.com/v1/datalab/search"

# 블로그 주제로 활용할 시드 키워드 카테고리
DEFAULT_SEED_KEYWORDS: list[dict[str, list[str]]] = [
    {"groupName": "육아", "keywords": ["아이와 가볼만한 곳", "키즈카페 추천", "아이 체험학습"]},
    {"groupName": "맛집/카페", "keywords": ["신상 카페", "대형카페 추천", "핫플 카페"]},
    {"groupName": "여행", "keywords": ["국내 여행지 추천", "가족 여행", "당일치기 여행"]},
    {"groupName": "생활정보", "keywords": ["주차장 추천", "전기차 보조금", "공영주차장 요금"]},
    {"groupName": "건강/음식", "keywords": ["제철 해산물", "제철 생선", "건강 음식 추천"]},
    {"groupName": "재테크", "keywords": ["적금 추천", "주식 초보", "부동산 전망"]},
    {"groupName": "자동차", "keywords": ["전기차 추천", "자동차 보험", "중고차 시세"]},
    {"groupName": "교육", "keywords": ["초등학생 학습", "영어 공부법", "독서 추천"]},
    {"groupName": "반려동물", "keywords": ["강아지 산책", "고양이 사료 추천", "반려동물 병원"]},
    {"groupName": "인테리어", "keywords": ["셀프 인테리어", "원룸 꾸미기", "가구 추천"]},
]


def _keys() -> tuple[str, str]:
    cid = os.getenv("NAVER_CLIENT_ID", "")
    csec = os.getenv("NAVER_CLIENT_SECRET", "")
    if not cid or not csec:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 .env 에 설정되어야 합니다.")
    return cid, csec


class DataLabApiError(RuntimeError):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((requests.RequestException, DataLabApiError)),
)
def _call(body: dict) -> dict:
    cid, csec = _keys()
    headers = {
        "X-Naver-Client-Id": cid,
        "X-Naver-Client-Secret": csec,
        "Content-Type": "application/json",
    }
    resp = requests.post(API_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 401:
        raise RuntimeError("네이버 API 인증 실패 (401). Client ID/Secret 확인 필요.")
    if resp.status_code >= 500:
        raise DataLabApiError(f"DataLab 5xx: {resp.status_code}")
    if resp.status_code != 200:
        raise DataLabApiError(f"DataLab {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _calc_trend_score(data_points: list[dict]) -> float:
    """최근 7일 평균 vs 이전 7일 평균으로 상승률 계산.

    Returns:
        상승률 (1.0 = 변화없음, 2.0 = 2배 상승, 0.5 = 반감)
    """
    if len(data_points) < 7:
        ratios = [d.get("ratio", 0) for d in data_points]
        return sum(ratios) / len(ratios) if ratios else 0

    recent = data_points[-7:]
    previous = data_points[-14:-7] if len(data_points) >= 14 else data_points[:7]

    avg_recent = sum(d.get("ratio", 0) for d in recent) / len(recent)
    avg_previous = sum(d.get("ratio", 0) for d in previous) / len(previous)

    if avg_previous <= 0:
        return avg_recent if avg_recent > 0 else 0
    return avg_recent / avg_previous


def fetch_trending_keywords(
    seed_groups: list[dict[str, list[str]]] | None = None,
    days: int = 30,
    top_n: int = 5,
) -> list[dict]:
    """시드 키워드 그룹들의 검색 트렌드를 조회하고, 상승률 기준 TOP N 반환.

    DataLab API는 한 번에 5개 그룹까지만 조회 가능하므로 배치 처리.

    Returns:
        [{"group_name": str, "keywords": list[str], "trend_score": float,
          "avg_volume": float, "best_keyword": str}, ...]
    """
    groups = seed_groups or DEFAULT_SEED_KEYWORDS
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    all_results: list[dict] = []

    # 5개씩 배치 처리 (API 제한)
    for i in range(0, len(groups), 5):
        batch = groups[i : i + 5]
        keyword_groups = [
            {"groupName": g["groupName"], "keywords": g["keywords"]}
            for g in batch
        ]

        body = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "timeUnit": "date",
            "keywordGroups": keyword_groups,
        }

        try:
            data = _call(body)
        except Exception:
            continue

        for result in data.get("results", []):
            title = result.get("title", "")
            points = result.get("data", [])
            keywords = result.get("keywords", [])

            # 원본 그룹에서 keywords 복원
            orig = next((g for g in batch if g["groupName"] == title), None)
            kw_list = orig["keywords"] if orig else keywords

            trend_score = _calc_trend_score(points)
            ratios = [d.get("ratio", 0) for d in points]
            avg_vol = sum(ratios) / len(ratios) if ratios else 0

            # 대표 키워드: 그룹의 첫 번째 키워드
            best_kw = kw_list[0] if kw_list else title

            all_results.append({
                "group_name": title,
                "keywords": kw_list,
                "trend_score": round(trend_score, 3),
                "avg_volume": round(avg_vol, 1),
                "best_keyword": best_kw,
            })

    # 상승률 * 검색량 복합 점수로 정렬
    all_results.sort(
        key=lambda x: x["trend_score"] * (x["avg_volume"] + 1),
        reverse=True,
    )
    return all_results[:top_n]


def build_seed_from_custom(keywords: list[str]) -> list[dict[str, list[str]]]:
    """사용자 입력 키워드를 시드 그룹으로 변환. 각 키워드가 하나의 그룹."""
    return [
        {"groupName": kw.strip(), "keywords": [kw.strip()]}
        for kw in keywords
        if kw.strip()
    ]
