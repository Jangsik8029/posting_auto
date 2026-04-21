"""Streamlit 엔트리포인트. 렌더링/동작은 ui_views/ 아래 모듈에 위임한다."""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import streamlit as st

from ui_views.actions import (
    handle_bulk_schedule,
    handle_publish_now,
    handle_reoptimize,
    handle_schedule_one,
)
from ui_views.inputs import render_inputs_panel
from ui_views.scheduler import get_scheduler
from ui_views.settings import load_ui_settings


def _render_scheduled_jobs(scheduler) -> None:
    st.subheader("Scheduled jobs")
    jobs = scheduler.get_jobs()
    if not jobs:
        st.caption("No scheduled jobs.")
        return
    for job in jobs:
        st.write(f"- `{job.id}`")
        st.caption(f"Next run: {job.next_run_time}")


def _render_bulk_template_download() -> None:
    template_path = Path(__file__).parent / "bulk_schedule_template.csv"
    if not template_path.exists():
        return
    st.download_button(
        "템플릿 CSV 다운로드",
        data=template_path.read_text(encoding="utf-8"),
        file_name="bulk_schedule_template.csv",
        mime="text/csv",
    )


def main() -> None:
    st.set_page_config(page_title="Blog Publisher", page_icon="📝", layout="wide")
    st.title("Blog Publisher UI")
    st.caption("Now publish + schedule publish + bulk schedule by Excel")

    saved = load_ui_settings()
    scheduler = get_scheduler()
    left, right = st.columns([2, 1])

    with left:
        values = render_inputs_panel(saved)

        st.markdown("### Run now")
        run_now = st.button("Publish now", type="primary")

        st.markdown("### Schedule one")
        run_date = st.date_input("Date", value=date.today())
        run_time = st.time_input("Time", value=time(hour=9, minute=0))
        schedule_one = st.button("Add schedule")

        st.markdown("### Schedule bulk (CSV / Excel)")
        st.caption(
            "필수: topic, run_at | 선택: main_topic, sub_topics, prompt_folder, "
            "image_count, status, model, with_image, image_source, submit_search, sitemap_url"
        )
        _render_bulk_template_download()
        uploaded_file = st.file_uploader("CSV 또는 Excel 업로드", type=["csv", "xlsx"])
        schedule_bulk = st.button("Register bulk schedules")

        st.markdown("### 기존 글 네이버 SEO 재적용")
        st.caption(
            "워드프레스 글 ID를 입력하면 제목·요약 길이, H1→H2, 이미지 alt를 "
            "네이버 가이드에 맞게 보정 후 저장합니다."
        )
        reopt_post_id = st.number_input("WordPress 글 ID", min_value=1, value=1, step=1, key="reopt_post_id")
        reoptimize_click = st.button("네이버 SEO 재적용")

    with right:
        _render_scheduled_jobs(scheduler)

    if run_now:
        handle_publish_now(values)
    if schedule_one:
        handle_schedule_one(values, scheduler, datetime.combine(run_date, run_time))
    if schedule_bulk:
        handle_bulk_schedule(values, scheduler, uploaded_file)
    if reoptimize_click:
        handle_reoptimize(values, int(reopt_post_id))


if __name__ == "__main__":
    main()
