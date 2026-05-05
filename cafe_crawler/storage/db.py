import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, Iterator

from cafe_crawler.config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    run_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    title TEXT,
    url TEXT NOT NULL,
    snippet TEXT,
    cafe_name TEXT,
    cafe_url TEXT,
    posted_at TEXT,
    rank INTEGER,
    score REAL,
    UNIQUE(search_id, url)
);

CREATE INDEX IF NOT EXISTS idx_posts_search ON posts(search_id);
CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(query);

CREATE TABLE IF NOT EXISTS published (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    candidate_rank INTEGER NOT NULL,
    main_topic TEXT NOT NULL,
    sub_topics TEXT,
    prompt_folder TEXT NOT NULL,
    wp_post_id INTEGER,
    wp_link TEXT,
    status TEXT,
    posted_at TEXT NOT NULL,
    UNIQUE(search_id, main_topic, prompt_folder)
);

CREATE INDEX IF NOT EXISTS idx_published_search ON published(search_id);
"""


_schema_ready = False


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    global _schema_ready
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not _schema_ready:
        conn.executescript(SCHEMA)
        _schema_ready = True
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def create_search(query: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO searches (query, run_at) VALUES (?, ?)",
            (query, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def save_posts(search_id: int, posts: Iterable[dict]) -> int:
    rows = [
        (
            search_id,
            p["platform"],
            p.get("title"),
            p["url"],
            p.get("snippet"),
            p.get("cafe_name"),
            p.get("cafe_url"),
            p.get("posted_at"),
            p.get("rank"),
            p.get("score"),
        )
        for p in posts
        if p.get("url")
    ]
    if not rows:
        return 0
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO posts
                (search_id, platform, title, url, snippet, cafe_name,
                 cafe_url, posted_at, rank, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(search_id, url) DO UPDATE SET
                title=excluded.title,
                snippet=excluded.snippet,
                cafe_name=excluded.cafe_name,
                cafe_url=excluded.cafe_url,
                posted_at=excluded.posted_at,
                rank=excluded.rank,
                score=excluded.score
            """,
            rows,
        )
    return len(rows)


def fetch_search(search_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM searches WHERE id = ?", (search_id,)
        ).fetchone()


def fetch_posts(search_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM posts WHERE search_id = ? ORDER BY score DESC NULLS LAST, rank ASC",
            (search_id,),
        ).fetchall()


def latest_search_id(query: str) -> int | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM searches WHERE query = ? ORDER BY run_at DESC LIMIT 1",
            (query,),
        ).fetchone()
        return row["id"] if row else None


def list_searches(limit: int = 50) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT s.id, s.query, s.run_at, COUNT(p.id) AS post_count
            FROM searches s
            LEFT JOIN posts p ON p.search_id = s.id
            GROUP BY s.id
            ORDER BY s.run_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def update_post_scores(scores: dict[int, float]) -> None:
    if not scores:
        return
    with connect() as conn:
        conn.executemany(
            "UPDATE posts SET score = ? WHERE id = ?",
            [(score, pid) for pid, score in scores.items()],
        )


def is_already_published(search_id: int, main_topic: str, prompt_folder: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM published WHERE search_id=? AND main_topic=? AND prompt_folder=?",
            (search_id, main_topic, prompt_folder),
        ).fetchone()
        return row is not None


def record_publication(
    search_id: int,
    candidate_rank: int,
    main_topic: str,
    sub_topics: list[str],
    prompt_folder: str,
    wp_post_id: int | None,
    wp_link: str | None,
    status: str | None,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO published
                (search_id, candidate_rank, main_topic, sub_topics, prompt_folder,
                 wp_post_id, wp_link, status, posted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(search_id, main_topic, prompt_folder) DO UPDATE SET
                candidate_rank=excluded.candidate_rank,
                sub_topics=excluded.sub_topics,
                wp_post_id=excluded.wp_post_id,
                wp_link=excluded.wp_link,
                status=excluded.status,
                posted_at=excluded.posted_at
            """,
            (
                search_id,
                candidate_rank,
                main_topic,
                ",".join(sub_topics) if sub_topics else "",
                prompt_folder,
                wp_post_id,
                wp_link,
                status,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cur.lastrowid or 0
