"""publish_post 오퍼레이션의 정상 경로 스모크. 외부 API는 모두 모킹한다."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from blogbot.config import AppConfig
from blogbot.models import Article
from blogbot.workflows import publish as publish_mod


def _base_args() -> SimpleNamespace:
    return SimpleNamespace(
        topic="강릉 맛집",
        main_topic="강릉 맛집",
        sub_topics="초당순두부",
        prompt_folder="default",
        image_count=2,
        status="draft",
        model="gpt-4o-mini",
        with_image=False,
        image_source="local",
        openai_api_key="sk-test",
        wp_domain="example.com",
        wp_user="admin",
        wp_app_password="pw",
        pixabay_api_key=None,
        submit_search=False,
        sitemap_url="",
        collect_only=False,
        collect_url="",
        knowledge_db_path="data/knowledge.db",
        knowledge_keyword="",
    )


@pytest.fixture
def mocked_publish(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """publish_post 경로에서 네트워크 함수들을 순수 파이썬 스텁으로 치환."""
    calls: dict[str, Any] = {}

    def fake_collect(main_topic: str, sub_topics: list[str], max_links: int = 5) -> list[dict[str, str]]:
        calls["collect"] = (main_topic, list(sub_topics), max_links)
        return [{"title": "ref-title", "url": "https://ref.example/x"}]

    def fake_search_knowledge(*_args: Any, **_kwargs: Any) -> list[dict[str, str]]:
        return []

    def fake_generate(
        main_topic: str,
        sub_topics: list[str],
        prompt_folder: str,
        references: list[dict[str, str]],
        api_key: str,
        model: str,
    ) -> Article:
        calls["generate"] = {
            "main_topic": main_topic,
            "prompt_folder": prompt_folder,
            "ref_count": len(references),
            "model": model,
        }
        return Article(
            title="강릉 맛집 가이드",
            excerpt="강릉 여행에서 꼭 들러야 할 맛집을 정리했습니다.",
            content_html="<h2>초당순두부</h2><p>내용</p>",
            seo_keyword="강릉 맛집",
        )

    def fake_post_to_wp(domain: str, wp_user: str, wp_app_password: str, article: Article, status: str) -> dict[str, Any]:
        calls["wp_post"] = {"domain": domain, "status": status, "title": article.title}
        return {"id": 1234, "link": f"https://{domain}/?p=1234", "slug": "gangneung"}

    def fake_choose_url(domain: str, created: dict[str, Any]) -> tuple[str, str]:
        return (str(created["link"]), f"https://{domain}/{created.get('slug', '')}")

    def fake_submit(public_url: str, sitemap_url: str = "") -> dict[str, str]:
        calls["submit"] = public_url
        return {"google": "ok", "bing": "ok", "naver": "skipped"}

    monkeypatch.setattr(publish_mod, "collect_reference_material", fake_collect)
    monkeypatch.setattr(publish_mod, "search_knowledge", fake_search_knowledge)
    monkeypatch.setattr(publish_mod, "generate_article_with_chatgpt", fake_generate)
    monkeypatch.setattr(publish_mod, "post_to_wordpress", fake_post_to_wp)
    monkeypatch.setattr(publish_mod, "choose_public_url", fake_choose_url)
    monkeypatch.setattr(publish_mod, "submit_post_to_search_sites", fake_submit)
    return calls


def test_publish_post_without_image_happy_path(mocked_publish: dict[str, Any]) -> None:
    cfg = AppConfig.from_args(_base_args())

    result = publish_mod.publish_post(cfg)

    assert result["post_id"] == "1234"
    assert result["title"] == "강릉 맛집 가이드"
    assert result["seo_keyword"] == "강릉 맛집"
    assert result["reference_count"] == "1"
    assert result["image_status"] == "not_requested"
    assert result["featured_image_status"] == "not_set"
    assert result["public_url"].startswith("https://example.com")
    assert "edit_url" in result and "post=1234" in result["edit_url"]
    assert mocked_publish["generate"]["ref_count"] == 1


def test_publish_post_with_image_title_source(
    mocked_publish: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    args = _base_args()
    args.with_image = True
    args.image_source = "title"
    args.image_count = 2
    cfg = AppConfig.from_args(args)

    def fake_thumbnail(label: str, index: int = 1) -> Any:
        out = tmp_path / f"thumb-{index}.jpg"
        out.write_bytes(b"fake-bytes")
        return out

    uploaded: list[Any] = []

    def fake_upload(domain: str, wp_user: str, wp_app_password: str, file_path: Any) -> dict[str, Any]:
        uploaded.append(file_path)
        return {"url": f"https://{domain}/uploads/{file_path.name}", "id": 900 + len(uploaded)}

    def fake_set_featured(**kwargs: Any) -> None:
        mocked_publish["featured"] = kwargs

    monkeypatch.setattr(publish_mod, "save_title_thumbnail", fake_thumbnail)
    monkeypatch.setattr(publish_mod, "upload_media_xmlrpc", fake_upload)
    monkeypatch.setattr(publish_mod, "set_featured_media", fake_set_featured)

    result = publish_mod.publish_post(cfg)

    assert len(uploaded) == 2
    assert result["image_status"] == "uploaded"
    assert result["image_count_uploaded"] == "2"
    assert result["featured_image_status"] == "set"
    assert mocked_publish["featured"]["post_id"] == 1234
    assert mocked_publish["featured"]["attachment_id"] == 901
