from pathlib import Path

from cafe_crawler.config import KNOWLEDGE_DB_PATH
from cafe_crawler.storage import fetch_posts
from blogbot.integrations.knowledge_collector import CollectedItem
from blogbot.integrations.knowledge_db import upsert_knowledge_items


def _to_item(post: dict) -> CollectedItem | None:
    page_url = (post.get("url") or "").strip()
    title = (post.get("title") or "").strip()
    if not page_url or not title:
        return None
    source_url = (post.get("cafe_url") or "").strip() or page_url
    body = (post.get("snippet") or "").strip()
    if not body:
        cafe = (post.get("cafe_name") or "").strip()
        body = f"{cafe} / {title}" if cafe else title
    return CollectedItem(source_url=source_url, title=title, body=body, link=page_url)


def export_to_knowledge_db(
    search_id: int, knowledge_db_path: Path | None = None, max_items: int = 200
) -> int:
    """크롤링 검색의 게시글을 posting_auto knowledge.db로 UPSERT.

    posting_auto의 upsert_knowledge_items 를 그대로 사용 (동일 프로젝트이므로 직접 import).
    """
    target = knowledge_db_path or KNOWLEDGE_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    posts = [dict(r) for r in fetch_posts(search_id)]
    if not posts:
        return 0

    items: list[CollectedItem] = []
    for p in posts[:max_items]:
        it = _to_item(p)
        if it:
            items.append(it)
    if not items:
        return 0

    return upsert_knowledge_items(str(target), items)
