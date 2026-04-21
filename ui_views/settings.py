"""UI 입력값을 로컬 파일에 저장/복원한다. 시크릿 키는 저장하지 않는다."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

SETTINGS_PATH = Path(__file__).resolve().parent.parent / ".posting_auto_ui_settings.json"

PERSISTED_SETTINGS_KEYS: frozenset[str] = frozenset({
    "topic",
    "main_topic",
    "sub_topics",
    "prompt_folder",
    "image_count",
    "status",
    "model",
    "with_image",
    "image_source",
    "submit_search",
    "sitemap_url",
    "knowledge_db_path",
    "knowledge_keyword",
})

FORBIDDEN_SETTINGS_KEYS: frozenset[str] = frozenset({
    "openai_api_key",
    "wp_domain",
    "wp_user",
    "wp_app_password",
    "pixabay_api_key",
})


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_ui_settings() -> dict[str, Any]:
    """저장된 UI 설정을 읽는다. 시크릿 키는 무시하고, 타입도 정규화한다."""
    if not SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    dropped = [k for k in raw if k in FORBIDDEN_SETTINGS_KEYS]
    cleaned: dict[str, Any] = {k: v for k, v in raw.items() if k in PERSISTED_SETTINGS_KEYS}
    if "with_image" in cleaned:
        cleaned["with_image"] = _coerce_bool(cleaned["with_image"], True)
    if "submit_search" in cleaned:
        cleaned["submit_search"] = _coerce_bool(cleaned["submit_search"], False)
    if "image_count" in cleaned:
        cleaned["image_count"] = _coerce_int(cleaned["image_count"], 4)

    if dropped:
        try:
            st.warning(
                "이전에 저장된 크리덴셜 값이 감지되어 무시했습니다. "
                f"해당 키: {', '.join(dropped)}. 설정을 다시 저장하면 파일에서 제거됩니다."
            )
        except Exception:
            pass
    return cleaned


def save_ui_settings(data: dict[str, Any]) -> None:
    """UI 입력값을 파일에 저장한다. 시크릿 키는 제외된다."""
    cleaned = {k: v for k, v in data.items() if k in PERSISTED_SETTINGS_KEYS}
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
