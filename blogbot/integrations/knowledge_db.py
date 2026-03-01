from __future__ import annotations

import sqlite3
from pathlib import Path

from blogbot.integrations.knowledge_collector import CollectedItem


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT NOT NULL,
    page_url TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_url, page_url)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_source_url ON knowledge_items(source_url);
CREATE INDEX IF NOT EXISTS idx_knowledge_title ON knowledge_items(title);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def upsert_knowledge_items(db_path: str, items: list[CollectedItem]) -> int:
    if not items:
        return 0
    sql = """
    INSERT INTO knowledge_items (source_url, page_url, title, body)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(source_url, page_url) DO UPDATE SET
        title = excluded.title,
        body = excluded.body,
        created_at = datetime('now')
    """
    with _connect(db_path) as conn:
        conn.executemany(
            sql,
            [(item.source_url, item.link, item.title, item.body) for item in items],
        )
        conn.commit()
    return len(items)


def search_knowledge(db_path: str, keyword: str, limit: int = 5) -> list[dict[str, str]]:
    like = f"%{keyword.strip()}%"
    sql = """
    SELECT title, page_url, source_url
    FROM knowledge_items
    WHERE title LIKE ? OR body LIKE ?
    ORDER BY created_at DESC, id DESC
    LIMIT ?
    """
    with _connect(db_path) as conn:
        rows = conn.execute(sql, (like, like, limit)).fetchall()
    return [{"title": str(r["title"]), "url": str(r["page_url"]), "source_url": str(r["source_url"])} for r in rows]
