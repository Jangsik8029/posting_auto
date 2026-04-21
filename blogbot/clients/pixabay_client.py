import logging
from pathlib import Path

import requests

from blogbot.clients.http import TIMEOUT_DEFAULT, get_shared_session
from blogbot.utils import download_bytes, ensure_downloads_dir, retry_with_backoff, safe_ascii_filename, truncate_with_ellipsis

logger = logging.getLogger(__name__)

PIXABAY_API_URL = "https://pixabay.com/api/"


@retry_with_backoff(max_attempts=3)
def _search_pixabay(params: dict) -> requests.Response:
    return get_shared_session().get(PIXABAY_API_URL, params=params, timeout=TIMEOUT_DEFAULT)


def fetch_pixabay_image_candidates(topic_query: str, pixabay_api_key: str, per_page: int = 20) -> list[dict]:
    params = {
        "key": pixabay_api_key,
        "q": topic_query,
        "image_type": "photo",
        "safesearch": "true",
        "per_page": per_page,
        "lang": "ko",
    }
    search_resp = _search_pixabay(params)
    if search_resp.status_code != 200:
        logger.debug("Pixabay search response: %s", search_resp.text)
        raise RuntimeError(
            f"Pixabay search failed ({search_resp.status_code}): "
            f"{truncate_with_ellipsis(search_resp.text, 300)}"
        )
    data = search_resp.json()
    return data.get("hits") or []


def download_images_with_pixabay(topic_query: str, pixabay_api_key: str, count: int = 4) -> list[tuple[bytes, str]]:
    hits = fetch_pixabay_image_candidates(topic_query, pixabay_api_key, per_page=max(20, count * 4))
    if not hits:
        raise RuntimeError("Pixabay returned no images for this topic.")

    collected: list[tuple[bytes, str]] = []
    seen: set[str] = set()
    session = get_shared_session()
    for selected in hits:
        image_url = (
            selected.get("webformatURL")
            or selected.get("previewURL")
            or selected.get("largeImageURL")
            or ""
        ).strip()
        if not image_url or image_url in seen:
            continue
        seen.add(image_url)
        image_bytes = download_bytes(image_url, timeout=40, session=session)
        if image_bytes is None:
            logger.warning("Pixabay image download failed: %s", image_url)
            continue
        collected.append((image_bytes, image_url))
        if len(collected) >= count:
            break

    if not collected:
        raise RuntimeError("Pixabay image downloads failed for all candidates.")
    return collected


def save_image_locally(image_bytes: bytes, topic: str, ext: str = "jpg", index: int = 1) -> Path:
    out_dir = ensure_downloads_dir()
    out_path = out_dir / f"{safe_ascii_filename(topic)}-{index}.{ext}"
    out_path.write_bytes(image_bytes)
    return out_path
