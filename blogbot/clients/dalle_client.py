from pathlib import Path

import requests

from blogbot.utils import safe_ascii_filename

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
        resp = requests.post(OPENAI_IMAGES_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError(f"DALL-E image generation failed ({resp.status_code}): {resp.text[:500]}")

        data = resp.json()
        image_url = data["data"][0].get("url", "")
        if not image_url:
            continue

        img_resp = requests.get(image_url, timeout=60)
        if img_resp.status_code != 200:
            continue
        collected.append((img_resp.content, image_url))

    if not collected:
        raise RuntimeError("DALL-E image generation produced no usable images.")
    return collected


def save_dalle_image_locally(image_bytes: bytes, topic: str, index: int = 1) -> Path:
    out_dir = Path("downloads")
    out_dir.mkdir(parents=True, exist_ok=True)
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
