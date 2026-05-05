from collections import Counter
from functools import lru_cache

STOPWORDS = {
    "오늘", "내일", "어제", "이번", "다음", "지금", "정말", "진짜", "하나",
    "사람", "정도", "경우", "때문", "생각", "이거", "저거", "그거", "이번에",
    "여기", "거기", "저기", "이런", "저런", "그런", "관련", "필요", "사용",
    "방법", "이상", "이하", "위해", "통해", "대한", "관한", "처음", "마지막",
    "문제", "이야기", "내용", "정보", "결과", "시간", "동안", "후기", "공유",
    "추천", "질문", "도움", "하루",
}


@lru_cache(maxsize=1)
def _kiwi():
    from kiwipiepy import Kiwi
    return Kiwi()


def _is_meaningful(token) -> bool:
    if token.tag not in ("NNG", "NNP", "SL"):
        return False
    if len(token.form) < 2:
        return False
    if token.form in STOPWORDS:
        return False
    return True


def _query_tokens(query: str) -> set[str]:
    if not query:
        return set()
    kiwi = _kiwi()
    tokens = {t.form for t in kiwi.tokenize(query) if _is_meaningful(t)}
    tokens.add(query.strip())
    return {t for t in tokens if t}


def extract_keywords(
    titles: list[str],
    top_n: int = 30,
    exclude: set[str] | None = None,
    query: str | None = None,
) -> list[tuple[str, int]]:
    """제목 리스트에서 명사/고유명사/외국어 단어 빈도 TOP N.

    검색어 노이즈 제거를 위해 두 단계로 필터링:
      1) `query` 가 주어지면 각 제목에서 검색어 문자열을 우선 제거
      2) `exclude` 에 포함된 토큰을 결과에서 제외
    """
    if not titles:
        return []
    kiwi = _kiwi()
    skip = exclude or set()
    counter: Counter[str] = Counter()
    q = (query or "").strip()
    for title in titles:
        if not title:
            continue
        cleaned = title
        if q:
            cleaned = cleaned.replace(q, " ")
            for part in q.split():
                if len(part) >= 2:
                    cleaned = cleaned.replace(part, " ")
        for token in kiwi.tokenize(cleaned):
            if _is_meaningful(token) and token.form not in skip:
                counter[token.form] += 1
    return counter.most_common(top_n)
