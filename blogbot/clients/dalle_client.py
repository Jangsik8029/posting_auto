import logging
from pathlib import Path

import requests

from blogbot.clients.http import TIMEOUT_LONG, get_shared_session
from blogbot.utils import download_bytes, ensure_downloads_dir, retry_with_backoff, safe_ascii_filename, truncate_with_ellipsis

logger = logging.getLogger(__name__)

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")

TOPIC_PROMPT_TEMPLATE = (
    "고품질 블로그 대표 이미지. "
    "주제: {topic}. "
    "밝고 선명한 색감, 자연광, 깔끔한 구도의 사진풍 이미지. "
    "텍스트·글자·워터마크 없이, 주제를 직관적으로 전달하는 한 장의 사진."
)


def _build_image_prompt(topic: str) -> str:
    return TOPIC_PROMPT_TEMPLATE.format(topic=topic)


@retry_with_backoff(max_attempts=3)
def _post_generate(headers: dict, payload: dict) -> requests.Response:
    return get_shared_session().post(
        OPENAI_IMAGES_URL, headers=headers, json=payload, timeout=TIMEOUT_LONG
    )


def generate_images_with_dalle(
    topic: str,
    api_key: str,
    count: int = 4,
    size: str = "1024x1024",
    quality: str = "standard",
) -> list[tuple[bytes, str]]:
    """DALL-E 3으로 주제 기반 이미지를 생성하고 바이트로 반환한다."""
    prompt = _build_image_prompt(topic)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    collected: list[tuple[bytes, str]] = []

    for _ in range(count):
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
        }
        resp = _post_generate(headers, payload)
        if resp.status_code != 200:
            logger.debug("DALL-E response body: %s", resp.text)
            raise RuntimeError(
                f"DALL-E image generation failed ({resp.status_code}): "
                f"{truncate_with_ellipsis(resp.text, 500)}"
            )

        data = resp.json()
        try:
            image_url = (data["data"][0] or {}).get("url", "")
        except (IndexError, KeyError, TypeError):
            logger.warning("DALL-E response missing data[0].url: %s", data)
            continue
        if not image_url:
            continue

        image_bytes = download_bytes(image_url, timeout=60, session=get_shared_session())
        if image_bytes is None:
            logger.warning("DALL-E image download failed for %s", image_url)
            continue
        collected.append((image_bytes, image_url))

    if not collected:
        raise RuntimeError("DALL-E image generation produced no usable images.")
    return collected


def save_dalle_image_locally(image_bytes: bytes, topic: str, index: int = 1) -> Path:
    out_dir = ensure_downloads_dir()
    out_path = out_dir / f"{safe_ascii_filename(topic)}-dalle-{index}.png"
    out_path.write_bytes(image_bytes)
    return out_path


def load_local_images(prompt_dir: Path, count: int = 5) -> list[Path]:
    """프롬프트 폴더에 저장된 이미지 파일을 찾아 최대 count개 반환한다."""
    images = sorted(
        [f for f in prompt_dir.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda p: p.name,
    )
    return images[:count]
