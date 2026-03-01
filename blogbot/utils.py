import json
import re
from datetime import datetime
from typing import Any


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

