"""AppConfig.from_args / validate 기본 동작 스모크."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from blogbot.config import AppConfig, ConfigValidationError


def _args(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "topic": "강릉 맛집",
        "main_topic": "강릉 맛집",
        "sub_topics": "초당순두부, 카페",
        "prompt_folder": "default",
        "image_count": 4,
        "status": "draft",
        "model": "gpt-4o-mini",
        "with_image": False,
        "image_source": "local",
        "openai_api_key": "sk-test",
        "wp_domain": "example.com",
        "wp_user": "admin",
        "wp_app_password": "pw",
        "pixabay_api_key": None,
        "submit_search": False,
        "sitemap_url": "",
        "collect_only": False,
        "collect_url": "",
        "knowledge_db_path": "data/knowledge.db",
        "knowledge_keyword": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_from_args_trims_and_splits_subtopics() -> None:
    cfg = AppConfig.from_args(_args(sub_topics=" a ,b, ,c "))
    assert cfg.sub_topics == ["a", "b", "c"]


def test_from_args_clamps_image_count() -> None:
    # 0은 falsy이므로 기본값 4로 대체되는 현재 동작 유지
    assert AppConfig.from_args(_args(image_count=0)).image_count == 4
    assert AppConfig.from_args(_args(image_count=-3)).image_count == 1
    assert AppConfig.from_args(_args(image_count=99)).image_count == 5


def test_from_args_collect_only_skips_wp_creds() -> None:
    args = _args(
        openai_api_key=None,
        wp_domain=None,
        wp_user=None,
        wp_app_password=None,
        collect_only=True,
        collect_url="https://example.com",
    )
    cfg = AppConfig.from_args(args)
    assert cfg.collect_only is True
    assert cfg.openai_api_key == ""
    assert cfg.wp_domain == ""


def test_validate_publish_missing_fields() -> None:
    cfg = AppConfig.from_args(_args(topic=""))
    with pytest.raises(ConfigValidationError) as exc:
        cfg.validate("publish")
    assert "topic" in str(exc.value)


def test_validate_publish_ok() -> None:
    cfg = AppConfig.from_args(_args())
    cfg.validate("publish")


def test_validate_reoptimize_only_requires_wp() -> None:
    cfg = AppConfig.from_args(_args(topic="", prompt_folder=""))
    cfg.validate("reoptimize")


def test_validate_collect_requires_url() -> None:
    args = _args(
        openai_api_key=None,
        wp_domain=None,
        wp_user=None,
        wp_app_password=None,
        collect_only=True,
        collect_url="",
    )
    cfg = AppConfig.from_args(args)
    with pytest.raises(ConfigValidationError):
        cfg.validate("collect")


def test_validate_unknown_operation() -> None:
    cfg = AppConfig.from_args(_args())
    with pytest.raises(ValueError):
        cfg.validate("unknown-op")


def test_validate_pixabay_required_when_selected() -> None:
    cfg = AppConfig.from_args(_args(with_image=True, image_source="local"))
    cfg.pixabay_api_key = ""
    cfg.validate("publish")  # local이면 pixabay 키 불필요

    cfg2 = AppConfig.from_args(_args(with_image=True, image_source="local"))
    cfg2.image_source = "pixabay"
    cfg2.pixabay_api_key = ""
    with pytest.raises(ConfigValidationError) as exc:
        cfg2.validate("publish")
    assert "pixabay_api_key" in str(exc.value)
