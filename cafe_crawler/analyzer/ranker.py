from collections import Counter
from datetime import datetime, timezone


def _sim_score(rank: int | None) -> float:
    if not rank or rank < 1:
        return 0.0
    return 1.0 / rank


def _recency_score(posted_at: str | None) -> float | None:
    if not posted_at:
        return None
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - dt).days
    if days <= 30:
        return 1.0
    if days <= 90:
        return 0.5
    if days <= 365:
        return 0.2
    return 0.0


def _normalize_cafe_freq(posts: list[dict]) -> dict[str, float]:
    counts = Counter(p.get("cafe_name") or "" for p in posts)
    if not counts:
        return {}
    max_count = max(counts.values())
    if max_count <= 1:
        return {name: 0.0 for name in counts}
    return {name: (c - 1) / (max_count - 1) for name, c in counts.items()}


def score_posts(posts: list[dict]) -> list[dict]:
    """Return new list of posts with `score` field populated.

    Score = 0.5 * sim + 0.3 * cafe_freq + 0.2 * recency
    Posts without recency (네이버) auto-renormalize to 0.625 / 0.375.
    """
    cafe_bonus = _normalize_cafe_freq(posts)
    out: list[dict] = []
    for p in posts:
        sim = _sim_score(p.get("rank"))
        freq = cafe_bonus.get(p.get("cafe_name") or "", 0.0)
        recency = _recency_score(p.get("posted_at"))
        if recency is None:
            score = 0.625 * sim + 0.375 * freq
        else:
            score = 0.5 * sim + 0.3 * freq + 0.2 * recency
        scored = dict(p)
        scored["score"] = round(score, 6)
        out.append(scored)
    return out
