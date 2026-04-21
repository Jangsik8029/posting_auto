"""발행/스케줄/재최적화 액션 핸들러."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler

from blogbot.config import AppConfig, ConfigValidationError
from blogbot.models import PublishResult
from blogbot.workflows.publish import publish_post
from blogbot.workflows.rewrite_seo import reoptimize_post_naver_seo

from ui_views.config_builder import build_config_from_inputs
from ui_views.inputs import InputValues
from ui_views.scheduler import parse_bulk_schedule, schedule_single_job

logger = logging.getLogger(__name__)


def _build_defaults(values: InputValues) -> dict[str, str]:
    return {
        "prompt_folder": values.prompt_folder,
        "image_count": str(values.image_count),
        "status": values.status,
        "model": values.model.strip() or "gpt-4o-mini",
        "with_image": str(values.with_image),
        "image_source": values.image_source,
        "submit_search": str(values.submit_search),
        "sitemap_url": values.sitemap_url.strip(),
        "openai_api_key": values.openai_api_key.strip(),
        "wp_domain": values.wp_domain.strip(),
        "wp_user": values.wp_user.strip(),
        "wp_app_password": values.wp_app_password.strip(),
        "pixabay_api_key": values.pixabay_api_key.strip(),
    }


def _build_config(values: InputValues, defaults: dict[str, str]) -> AppConfig:
    return build_config_from_inputs(
        topic=values.topic.strip(),
        main_topic=(values.main_topic.strip() or values.topic.strip()),
        sub_topics=values.sub_topics.strip(),
        prompt_folder=values.prompt_folder,
        image_count=values.image_count,
        status=defaults["status"],
        model=defaults["model"],
        with_image=values.with_image,
        image_source=defaults["image_source"],
        openai_api_key=defaults["openai_api_key"],
        wp_domain=defaults["wp_domain"],
        wp_user=defaults["wp_user"],
        wp_app_password=defaults["wp_app_password"],
        pixabay_api_key=defaults["pixabay_api_key"],
        submit_search=values.submit_search,
        sitemap_url=values.sitemap_url.strip(),
    )


def _render_result(result: PublishResult, with_image: bool, status: str) -> None:
    st.success("Post published.")
    st.write(f"Post ID: {result['post_id']}")
    st.write(f"Title: {result['title']}")
    st.write(f"SEO keyword: {result['seo_keyword']}")
    st.write(f"References used: {result['reference_count']}")
    st.link_button("Public link", result["public_url"])
    st.link_button("Edit link", result["edit_url"])

    if with_image:
        if result.get("image_url"):
            st.write(f"Images uploaded: {result['image_count_uploaded']}")
            st.caption(result["image_url"])
        else:
            st.warning(f"Image not inserted: {result.get('image_status')}")
            if result.get("image_message"):
                st.caption(result["image_message"])

    if result.get("featured_image_status"):
        st.caption(f"Featured image: {result['featured_image_status']}")

    if result.get("search_submit"):
        st.caption(f"Search submit: {result['search_submit']}")

    if status != "publish":
        st.info("Draft/private posts may not be visible on public URL.")


def handle_publish_now(values: InputValues) -> None:
    if not values.topic.strip():
        st.error("Topic is required.")
        return
    if not values.prompt_folder:
        st.error("Prompt folder is required.")
        return
    defaults = _build_defaults(values)
    try:
        config = _build_config(values, defaults)
        config.validate("publish")
        with st.spinner("Publishing..."):
            result = publish_post(config)
        _render_result(result, with_image=config.with_image, status=config.status)
    except ConfigValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        logger.exception("Publish failed")
        st.error(f"Failed: {exc}")


def handle_schedule_one(
    values: InputValues,
    scheduler: BackgroundScheduler,
    run_at: datetime,
) -> None:
    if not values.topic.strip():
        st.error("Topic is required.")
        return
    if not values.prompt_folder:
        st.error("Prompt folder is required.")
        return
    defaults = _build_defaults(values)
    try:
        config = _build_config(values, defaults)
        config.validate("publish")
        job_id = schedule_single_job(scheduler, config, run_at)
        st.success(f"Scheduled: {job_id} at {run_at}")
    except ConfigValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        logger.exception("Schedule single failed")
        st.error(f"Schedule failed: {exc}")


def handle_bulk_schedule(
    values: InputValues,
    scheduler: BackgroundScheduler,
    uploaded_file: Any | None,
) -> None:
    if uploaded_file is None:
        st.error("CSV 또는 Excel 파일을 업로드해주세요.")
        return
    defaults = _build_defaults(values)
    try:
        jobs = parse_bulk_schedule(uploaded_file.read(), uploaded_file.name, defaults)
        if not jobs:
            st.warning("No valid rows found in Excel.")
            return
        success_count = 0
        for config, run_at in jobs:
            schedule_single_job(scheduler, config, run_at)
            success_count += 1
        st.success(f"Bulk schedule registered: {success_count} jobs")
    except Exception as exc:
        logger.exception("Bulk schedule failed")
        st.error(f"Bulk schedule failed: {exc}")


def handle_reoptimize(values: InputValues, post_id: int) -> None:
    defaults = _build_defaults(values)
    try:
        result = reoptimize_post_naver_seo(
            domain=defaults["wp_domain"],
            wp_user=defaults["wp_user"],
            wp_app_password=defaults["wp_app_password"],
            post_id=post_id,
        )
        st.success("네이버 SEO 재적용 완료.")
        st.write(f"글 ID: {result['post_id']}")
        st.write(f"제목: {result['title']}")
        st.caption(f"요약 미리보기: {result['excerpt_preview']}")
    except Exception as exc:
        logger.exception("Reoptimize failed")
        st.error(f"재적용 실패: {exc}")
