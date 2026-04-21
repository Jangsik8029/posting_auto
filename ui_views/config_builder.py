"""UI 입력 → AppConfig 생성 헬퍼."""
from __future__ import annotations

from types import SimpleNamespace

from blogbot.config import AppConfig


def build_config_from_inputs(
    topic: str,
    main_topic: str,
    sub_topics: str,
    prompt_folder: str,
    image_count: int,
    status: str,
    model: str,
    with_image: bool,
    image_source: str,
    openai_api_key: str,
    wp_domain: str,
    wp_user: str,
    wp_app_password: str,
    pixabay_api_key: str,
    submit_search: bool,
    sitemap_url: str,
) -> AppConfig:
    args = SimpleNamespace(
        topic=topic,
        main_topic=main_topic,
        sub_topics=sub_topics,
        prompt_folder=prompt_folder,
        image_count=image_count,
        status=status,
        model=model,
        with_image=with_image,
        image_source=image_source,
        openai_api_key=openai_api_key or None,
        wp_domain=wp_domain or None,
        wp_user=wp_user or None,
        wp_app_password=wp_app_password or None,
        pixabay_api_key=pixabay_api_key or None,
        submit_search=submit_search,
        sitemap_url=sitemap_url,
    )
    return AppConfig.from_args(args)
