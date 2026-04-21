"""APScheduler 리소스 + 단건/벌크 스케줄 등록."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from blogbot.config import AppConfig
from blogbot.workflows.publish import publish_post

from ui_views.config_builder import build_config_from_inputs


def _job_publish(config_dict: dict[str, Any]) -> None:
    """APScheduler 가 스레드에서 실행하는 잡 엔트리."""
    config = AppConfig(**config_dict)
    publish_post(config)


@st.cache_resource
def get_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.start()
    return scheduler


def schedule_single_job(scheduler: BackgroundScheduler, config: AppConfig, run_at: datetime) -> str:
    if run_at <= datetime.now():
        raise ValueError("Scheduled time must be in the future.")
    job_id = f"publish-{int(run_at.timestamp())}-{abs(hash(config.topic)) % 10000}"
    scheduler.add_job(
        _job_publish,
        trigger=DateTrigger(run_date=run_at),
        args=[asdict(config)],
        id=job_id,
        replace_existing=True,
    )
    return job_id


_TRUTHY = {"1", "true", "yes", "y"}


def _row_bool(row: "pd.Series", key: str, default: str) -> bool:
    return str(row.get(key, default)).strip().lower() in _TRUTHY


def parse_bulk_schedule(
    content: bytes, filename: str, defaults: dict[str, str]
) -> list[tuple[AppConfig, datetime]]:
    """벌크 스케줄용 CSV 또는 Excel 파일을 파싱한다."""
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(BytesIO(content), encoding="utf-8")
    else:
        df = pd.read_excel(BytesIO(content))

    required_cols = {"topic", "run_at"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    jobs: list[tuple[AppConfig, datetime]] = []
    for idx, row in df.iterrows():
        topic = str(row.get("topic", "")).strip()
        if not topic:
            continue

        try:
            run_at = pd.to_datetime(row.get("run_at")).to_pydatetime()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {idx}: invalid run_at ({row.get('run_at')!r}): {exc}") from exc
        try:
            image_count = int(row.get("image_count", defaults["image_count"]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {idx}: invalid image_count ({row.get('image_count')!r}): {exc}") from exc

        main_topic = str(row.get("main_topic", topic)).strip() or topic
        sub_topics = str(row.get("sub_topics", "")).strip()
        prompt_folder = (
            str(row.get("prompt_folder", defaults["prompt_folder"])).strip() or defaults["prompt_folder"]
        )
        status = str(row.get("status", defaults["status"])).strip() or defaults["status"]
        model = str(row.get("model", defaults["model"])).strip() or defaults["model"]
        with_image = _row_bool(row, "with_image", defaults["with_image"])
        image_source = (
            str(row.get("image_source", defaults["image_source"])).strip().lower()
            or defaults["image_source"]
        )
        submit_search = _row_bool(row, "submit_search", defaults["submit_search"])
        sitemap_url = str(row.get("sitemap_url", defaults["sitemap_url"])).strip()

        config = build_config_from_inputs(
            topic=topic,
            main_topic=main_topic,
            sub_topics=sub_topics,
            prompt_folder=prompt_folder,
            image_count=image_count,
            status=status,
            model=model,
            with_image=with_image,
            image_source=image_source,
            openai_api_key=defaults["openai_api_key"],
            wp_domain=defaults["wp_domain"],
            wp_user=defaults["wp_user"],
            wp_app_password=defaults["wp_app_password"],
            pixabay_api_key=defaults["pixabay_api_key"],
            submit_search=submit_search,
            sitemap_url=sitemap_url,
        )
        jobs.append((config, run_at))

    return jobs
