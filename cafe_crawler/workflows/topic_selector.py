from dataclasses import dataclass, field

from cafe_crawler.analyzer import extract_keywords, query_tokens
from cafe_crawler.storage import fetch_posts, fetch_search


@dataclass
class TopicCandidate:
    rank: int
    main_topic: str
    sub_topics: list[str]
    representative_post_url: str
    representative_title: str
    source_keyword: str
    keyword_focus: str
    metadata: dict = field(default_factory=dict)


def _compose_main_topic(query: str, focus: str) -> str:
    q = (query or "").strip()
    f = (focus or "").strip()
    if not f:
        return q
    if f in q:
        return q
    return f"{q} - {f}"


def select_topics(search_id: int, top: int = 5) -> list[TopicCandidate]:
    search = fetch_search(search_id)
    if search is None:
        raise ValueError(f"search_id={search_id} 가 존재하지 않습니다.")

    posts = [dict(r) for r in fetch_posts(search_id)]
    if not posts:
        return []

    titles = [p.get("title") or "" for p in posts]
    query = search["query"]
    qtokens = query_tokens(query)

    keywords = extract_keywords(titles, top_n=20, exclude=qtokens, query=query)
    if not keywords:
        return []

    keyword_pool = [kw for kw, _ in keywords]

    candidates: list[TopicCandidate] = []
    used_post_urls: set[str] = set()
    rank = 0

    for focus_kw, _count in keywords:
        if rank >= top:
            break

        rep = _pick_representative(posts, focus_kw, used_post_urls)
        if rep is None:
            continue
        used_post_urls.add(rep["url"])

        sub = [k for k in keyword_pool if k != focus_kw][:5]

        rank += 1
        candidates.append(
            TopicCandidate(
                rank=rank,
                main_topic=_compose_main_topic(query, focus_kw),
                sub_topics=sub,
                representative_post_url=rep.get("url") or "",
                representative_title=rep.get("title") or "",
                source_keyword=query,
                keyword_focus=focus_kw,
                metadata={
                    "score": rep.get("score"),
                    "cafe_name": rep.get("cafe_name"),
                },
            )
        )

    return candidates


def _pick_representative(
    posts: list[dict], focus_kw: str, used_urls: set[str]
) -> dict | None:
    matches = [
        p
        for p in posts
        if focus_kw in (p.get("title") or "") and p.get("url") not in used_urls
    ]
    if not matches:
        return None
    matches.sort(key=lambda p: p.get("score") or 0.0, reverse=True)
    return matches[0]
