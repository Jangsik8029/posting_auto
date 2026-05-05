import re
from pathlib import Path

import pandas as pd

from cafe_crawler.analyzer import extract_keywords, query_tokens
from cafe_crawler.config import REPORTS_DIR, ensure_dirs
from cafe_crawler.storage.db import fetch_posts, fetch_search


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") or "report"


def _rows_to_records(rows) -> list[dict]:
    return [dict(r) for r in rows]


def export_csv(search_id: int, path: Path | None = None) -> Path:
    ensure_dirs()
    posts = _rows_to_records(fetch_posts(search_id))
    df = pd.DataFrame(posts)
    target = path or _default_path(search_id, "csv")
    df.to_csv(target, index=False, encoding="utf-8-sig")
    return target


def export_excel(search_id: int, path: Path | None = None) -> Path:
    ensure_dirs()
    posts = _rows_to_records(fetch_posts(search_id))
    df = pd.DataFrame(posts)
    target = path or _default_path(search_id, "xlsx")
    df.to_excel(target, index=False)
    return target


def export_markdown(search_id: int, top_n: int = 20, path: Path | None = None) -> Path:
    ensure_dirs()
    search = fetch_search(search_id)
    if search is None:
        raise ValueError(f"search_id={search_id} 가 존재하지 않습니다.")
    posts = _rows_to_records(fetch_posts(search_id))
    target = path or _default_path(search_id, "md")

    titles = [p.get("title") or "" for p in posts]
    keywords = extract_keywords(
        titles,
        top_n=10,
        exclude=query_tokens(search["query"]),
        query=search["query"],
    )

    lines: list[str] = []
    lines.append(f'# "{search["query"]}" 인기 카페 게시글 리포트')
    lines.append("")
    lines.append(f"- 실행 시각: {search['run_at']}")
    lines.append(f"- 수집 게시글: {len(posts)}건")
    lines.append("")
    lines.append("## 추천 블로그 주제 (제목 키워드 빈도 TOP 10)")
    lines.append("")
    if keywords:
        for i, (kw, cnt) in enumerate(keywords, 1):
            lines.append(f"{i}. **{kw}** — {cnt}회")
    else:
        lines.append("_추출된 키워드가 없습니다._")
    lines.append("")
    lines.append(f"## 인기 게시글 TOP {top_n}")
    lines.append("")
    lines.append("| 순위 | 플랫폼 | 제목 | 카페 | 점수 | 링크 |")
    lines.append("|---|---|---|---|---|---|")
    for i, p in enumerate(posts[:top_n], 1):
        title = (p.get("title") or "").replace("|", "\\|")
        cafe = (p.get("cafe_name") or "").replace("|", "\\|")
        score = p.get("score")
        score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
        url = p.get("url") or ""
        lines.append(
            f"| {i} | {p.get('platform')} | {title} | {cafe} | {score_str} | [열기]({url}) |"
        )
    lines.append("")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def _default_path(search_id: int, ext: str) -> Path:
    search = fetch_search(search_id)
    query = search["query"] if search else f"search{search_id}"
    run_at = (search["run_at"] if search else "").split("T")[0]
    name = f"{_safe_filename(query)}_{run_at}_{search_id}.{ext}"
    return REPORTS_DIR / name
