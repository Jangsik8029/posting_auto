"""knowledge_db 라운드트립 스모크."""
from __future__ import annotations

from pathlib import Path

from blogbot.integrations.knowledge_collector import CollectedItem
from blogbot.integrations.knowledge_db import search_knowledge, upsert_knowledge_items


def _item(page_url: str, title: str, body: str) -> CollectedItem:
    return CollectedItem(source_url="https://ex.com", title=title, body=body, link=page_url)


def test_upsert_inserts_and_upsert_updates(tmp_path: Path) -> None:
    db = tmp_path / "sub" / "k.db"

    n = upsert_knowledge_items(
        str(db),
        [
            _item("https://ex.com/a", "강릉 맛집 리스트", "초당순두부 정보"),
            _item("https://ex.com/b", "제주 카페", "커피 본문"),
        ],
    )
    assert n == 2
    assert db.exists()

    hits = search_knowledge(str(db), "강릉")
    assert len(hits) == 1
    assert hits[0]["url"] == "https://ex.com/a"

    # Re-insert same key → 제목 갱신, 중복 행 없음
    upsert_knowledge_items(
        str(db),
        [_item("https://ex.com/a", "강릉 맛집 업데이트판", "갱신 본문")],
    )
    hits = search_knowledge(str(db), "업데이트판")
    assert len(hits) == 1
    assert hits[0]["title"] == "강릉 맛집 업데이트판"


def test_upsert_empty_list_is_noop(tmp_path: Path) -> None:
    db = tmp_path / "k.db"
    assert upsert_knowledge_items(str(db), []) == 0
    # 빈 리스트는 파일 생성도 하지 않는다
    assert not db.exists()


def test_search_body_match(tmp_path: Path) -> None:
    db = tmp_path / "k.db"
    upsert_knowledge_items(
        str(db),
        [_item("https://ex.com/p", "제목 없음", "특이한키워드XYZ가 본문에 있음")],
    )
    hits = search_knowledge(str(db), "특이한키워드XYZ")
    assert len(hits) == 1
