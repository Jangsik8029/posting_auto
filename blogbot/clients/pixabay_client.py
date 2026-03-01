from pathlib import Path

import requests

from blogbot.utils import safe_ascii_filename

PIXABAY_API_URL = "https://pixabay.com/api/"


def fetch_pixabay_image_candidates(topic_query: str, pixabay_api_key: str, per_page: int = 20) -> list[dict]:
    params = {
        "key": pixabay_api_key,
        "q": topic_query,
        "image_type": "photo",
        "safesearch": "true",
        "per_page": per_page,
        "lang": "ko",
    }
    search_resp = requests.get(PIXABAY_API_URL, params=params, timeout=30)
    if search_resp.status_code != 200:
        raise RuntimeError(f"Pixabay search failed ({search_resp.status_code}): {search_resp.text[:300]}")
    data = search_resp.json()
    return data.get("hits") or []


def download_images_with_pixabay(topic_query: str, pixabay_api_key: str, count: int = 4) -> list[tuple[bytes, str]]:
    hits = fetch_pixabay_image_candidates(topic_query, pixabay_api_key, per_page=max(20, count * 4))
    if not hits:
        raise RuntimeError("Pixabay returned no images for this topic.")

    collected: list[tuple[bytes, str]] = []
    seen: set[str] = set()
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
        image_resp = requests.get(image_url, timeout=40)
        if image_resp.status_code != 200:
            continue
        collected.append((image_resp.content, image_url))
        if len(collected) >= count:
            break

    if not collected:
        raise RuntimeError("Pixabay image downloads failed for all candidates.")
    return collected


def save_image_locally(image_bytes: bytes, topic: str, ext: str = "jpg", index: int = 1) -> Path:
    out_dir = Path("downloads")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe_ascii_filename(topic)}-{index}.{ext}"
    out_path.write_bytes(image_bytes)
    return out_path

