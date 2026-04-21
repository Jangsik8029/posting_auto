from __future__ import annotations

import functools
import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def sanitize_app_password(raw: str) -> str:
    return "".join(raw.split())


def normalize_domain(raw: str) -> str:
    value = raw.strip()
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    return value.strip("/")


def slugify_korean_friendly(text: str) -> str:
    lowered = text.strip().lower()
    slug = re.sub(r"[^a-z0-9가-힣\s-]", "", lowered)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:80] if slug else "auto-post"


def safe_ascii_filename(text: str) -> str:
    raw = text.strip().lower()
    ascii_only = re.sub(r"[^a-z0-9\s-]", "", raw)
    ascii_only = re.sub(r"\s+", "-", ascii_only)
    ascii_only = re.sub(r"-{2,}", "-", ascii_only).strip("-")
    if ascii_only:
        return ascii_only[:60]
    return datetime.now().strftime("image-%Y%m%d-%H%M%S")


def extract_json_object(raw_text: str) -> dict[str, Any]:
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model output does not contain a valid JSON object.")
    return json.loads(raw_text[start : end + 1])


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """HTML 태그를 제거하고 엔티티를 언이스케이프한다."""
    import html as _html

    return _html.unescape(_HTML_TAG_RE.sub("", text)).strip()


def truncate_with_ellipsis(text: str, max_len: int, ellipsis: str = "…") -> str:
    """문자열이 max_len을 초과하면 말줄임표(…)로 잘라 반환한다."""
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= len(ellipsis):
        return text[:max_len]
    return text[: max_len - len(ellipsis)] + ellipsis


def ensure_downloads_dir(subdir: str | None = None) -> Path:
    """프로젝트의 `downloads/` 디렉터리를 보장 생성하고 반환한다."""
    base = Path("downloads")
    out = base / subdir if subdir else base
    out.mkdir(parents=True, exist_ok=True)
    return out


def download_bytes(
    url: str,
    timeout: int = 60,
    max_attempts: int = 3,
    session: Any = None,
) -> bytes | None:
    """URL에서 바이트를 다운로드한다. 실패 시 None 반환(로그 남김)."""
    import requests

    client = session if session is not None else requests
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.get(url, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                return resp.content
            logger.warning(
                "download_bytes: %s returned HTTP %s (attempt %s/%s)",
                url, resp.status_code, attempt, max_attempts,
            )
            if resp.status_code not in (408, 429, 500, 502, 503, 504):
                return None
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "download_bytes: exception for %s (attempt %s/%s): %s",
                url, attempt, max_attempts, exc,
            )
        if attempt < max_attempts:
            time.sleep(min(2 ** (attempt - 1) + random.random(), 8.0))
    if last_exc is not None:
        logger.warning("download_bytes: giving up on %s after %s attempts", url, max_attempts)
    return None


_RETRY_DEFAULT_STATUS = (408, 429, 500, 502, 503, 504)


def retry_with_backoff(
    max_attempts: int = 3,
    retry_on_status: tuple[int, ...] = _RETRY_DEFAULT_STATUS,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    지수 백오프 재시도 데코레이터. 감싸는 함수는 `requests.Response` 를 반환해야 한다.
    상태 코드가 retry_on_status에 포함되거나 requests.RequestException이 발생하면 재시도한다.
    """
    import requests

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                except requests.RequestException as exc:
                    last_exc = exc
                    logger.warning(
                        "%s: request exception on attempt %s/%s: %s",
                        func.__name__, attempt, max_attempts, exc,
                    )
                else:
                    status = getattr(result, "status_code", None)
                    if status is None or status not in retry_on_status:
                        return result
                    logger.warning(
                        "%s: HTTP %s on attempt %s/%s, retrying",
                        func.__name__, status, attempt, max_attempts,
                    )
                    last_exc = None
                if attempt < max_attempts:
                    delay = min(base_delay * (2 ** (attempt - 1)) + random.random(), max_delay)
                    time.sleep(delay)
            if last_exc is not None:
                raise last_exc
            return result  # type: ignore[return-value]
        return wrapper
    return decorator
