from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime, time
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from blogbot.clients.openai_client import list_prompt_folders
from blogbot.config import (
    INLINE_OPENAI_API_KEY,
    INLINE_PIXABAY_API_KEY,
    INLINE_WP_APP_PASSWORD,
    INLINE_WP_DOMAIN,
    INLINE_WP_USER,
    AppConfig,
)
from blogbot.workflows.publish import publish_post

# UI 입력 저장 파일 (프로젝트 루트, .gitignore 대상)
SETTINGS_PATH = Path(__file__).resolve().parent / ".posting_auto_ui_settings.json"


def load_ui_settings() -> dict[str, Any]:
    """저장된 UI 설정을 읽는다. 없거나 오류면 빈 dict."""
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_ui_settings(data: dict[str, Any]) -> None:
    """현재 UI 입력값을 파일에 저장한다."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _job_publish(config_dict: dict[str, Any]) -> None:
    config = AppConfig(**config_dict)
    publish_post(config)


@st.cache_resource
def get_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.start()
    return scheduler


def render_result(result: dict[str, str], with_image: bool, status: str) -> None:
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

    if result.get("search_submit"):
        st.caption(f"Search submit: {result['search_submit']}")

    if status != "publish":
        st.info("Draft/private posts may not be visible on public URL.")


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


def parse_bulk_schedule(content: bytes, filename: str, defaults: dict[str, str]) -> list[tuple[AppConfig, datetime]]:
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
    for _, row in df.iterrows():
        topic = str(row.get("topic", "")).strip()
        if not topic:
            continue

        run_at = pd.to_datetime(row.get("run_at")).to_pydatetime()
        main_topic = str(row.get("main_topic", topic)).strip() or topic
        sub_topics = str(row.get("sub_topics", "")).strip()
        prompt_folder = str(row.get("prompt_folder", defaults["prompt_folder"])).strip() or defaults["prompt_folder"]
        image_count = int(row.get("image_count", defaults["image_count"]))
        status = str(row.get("status", defaults["status"])).strip() or defaults["status"]
        model = str(row.get("model", defaults["model"])).strip() or defaults["model"]
        with_image = str(row.get("with_image", defaults["with_image"])).strip().lower() in {"1", "true", "yes", "y"}
        image_source = str(row.get("image_source", defaults["image_source"])).strip().lower() or defaults["image_source"]
        submit_search = str(row.get("submit_search", defaults["submit_search"])).strip().lower() in {"1", "true", "yes", "y"}
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


def main() -> None:
    st.set_page_config(page_title="Blog Publisher", page_icon="📝", layout="wide")
    st.title("Blog Publisher UI")
    st.caption("Now publish + schedule publish + bulk schedule by Excel")

    saved = load_ui_settings()
    _opt = lambda key, default: saved.get(key, default)

    scheduler = get_scheduler()
    left, right = st.columns([2, 1])

    with left:
        topic = st.text_input("Topic", placeholder="e.g. 5-year-old weekend play ideas", value=_opt("topic", ""))
        main_topic = st.text_input("Main topic", value=_opt("main_topic", ""))
        sub_topics = st.text_input("Sub topics (comma-separated)", value=_opt("sub_topics", ""))
        prompt_folders = list_prompt_folders()
        if not prompt_folders:
            st.warning("No prompt folders found under blogbot/prompt/. Add a subfolder with .txt files.")
        pf_saved = _opt("prompt_folder", "")
        pf_index = prompt_folders.index(pf_saved) if prompt_folders and pf_saved in prompt_folders else 0
        prompt_folder = st.selectbox(
            "Prompt folder (글 작성 가이드)",
            options=prompt_folders,
            index=pf_index,
        ) if prompt_folders else ""
        try:
            _ic = int(_opt("image_count", 4))
        except (TypeError, ValueError):
            _ic = 4
        image_count = st.slider("Image count", min_value=1, max_value=5, value=min(max(_ic, 1), 5))
        status_options = ["draft", "publish", "private"]
        status_index = status_options.index(_opt("status", "draft")) if _opt("status", "draft") in status_options else 0
        status = st.selectbox("Post status", status_options, index=status_index)
        model = st.text_input("OpenAI model", value=_opt("model", "gpt-4o-mini"))
        with_image = st.checkbox("이미지 포함", value=_opt("with_image", True) if isinstance(_opt("with_image", True), bool) else str(_opt("with_image", "true")).lower() in ("true", "1", "yes"))
        _source_labels = {
            "local": "로컬 (프롬프트 폴더)",
            "title": "제목 썸네일 (자동 생성, 무료)",
            "dalle": "DALL-E (AI 생성, 유료)",
            "pixabay": "Pixabay (스톡 검색)",
        }
        image_source_options = ["local", "title", "dalle", "pixabay"]
        is_saved = _opt("image_source", "local")
        is_index = image_source_options.index(is_saved) if is_saved in image_source_options else 0
        image_source = st.radio(
            "이미지 소스",
            options=image_source_options,
            format_func=lambda x: _source_labels[x],
            index=is_index,
            horizontal=True,
        )
        submit_search_val = _opt("submit_search", False)
        if isinstance(submit_search_val, bool):
            submit_search = st.checkbox("Submit sitemap to search engines", value=submit_search_val)
        else:
            submit_search = st.checkbox("Submit sitemap to search engines", value=str(submit_search_val).lower() in ("true", "1", "yes"))
        sitemap_url = st.text_input("Sitemap URL (optional)", value=_opt("sitemap_url", ""))

        with st.expander("Connection settings", expanded=False):
            openai_default = _opt("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "") or INLINE_OPENAI_API_KEY
            openai_api_key = st.text_input("OpenAI API Key", value=openai_default, type="password")
            wp_domain = st.text_input("WordPress Domain", value=_opt("wp_domain", INLINE_WP_DOMAIN))
            wp_user = st.text_input("WordPress User", value=_opt("wp_user", INLINE_WP_USER))
            wp_app_password = st.text_input("WordPress App Password", value=_opt("wp_app_password", INLINE_WP_APP_PASSWORD), type="password")
            pixabay_api_key = st.text_input("Pixabay API Key", value=_opt("pixabay_api_key", INLINE_PIXABAY_API_KEY), type="password")
            if st.button("현재 설정 저장 (다음부터 자동 불러옴)"):
                save_ui_settings({
                    "topic": topic,
                    "main_topic": main_topic,
                    "sub_topics": sub_topics,
                    "prompt_folder": prompt_folder,
                    "image_count": image_count,
                    "status": status,
                    "model": model,
                    "with_image": with_image,
                    "image_source": image_source,
                    "submit_search": submit_search,
                    "sitemap_url": sitemap_url,
                    "openai_api_key": openai_api_key,
                    "wp_domain": wp_domain,
                    "wp_user": wp_user,
                    "wp_app_password": wp_app_password,
                    "pixabay_api_key": pixabay_api_key,
                })
                st.success("저장되었습니다. 다음 실행부터 자동으로 불러옵니다.")

        st.markdown("### Run now")
        run_now = st.button("Publish now", type="primary")

        st.markdown("### Schedule one")
        run_date = st.date_input("Date", value=date.today())
        run_time = st.time_input("Time", value=time(hour=9, minute=0))
        schedule_one = st.button("Add schedule")

        st.markdown("### Schedule bulk (CSV / Excel)")
        st.caption("필수: topic, run_at | 선택: main_topic, sub_topics, prompt_folder, image_count, status, model, with_image, image_source, submit_search, sitemap_url")
        try:
            template_path = Path(__file__).parent / "bulk_schedule_template.csv"
            if template_path.exists():
                st.download_button(
                    "템플릿 CSV 다운로드",
                    data=template_path.read_text(encoding="utf-8"),
                    file_name="bulk_schedule_template.csv",
                    mime="text/csv",
                )
        except Exception:
            pass
        uploaded_file = st.file_uploader("CSV 또는 Excel 업로드", type=["csv", "xlsx"])
        schedule_bulk = st.button("Register bulk schedules")

    with right:
        st.subheader("Scheduled jobs")
        jobs = scheduler.get_jobs()
        if not jobs:
            st.caption("No scheduled jobs.")
        else:
            for job in jobs:
                st.write(f"- `{job.id}`")
                st.caption(f"Next run: {job.next_run_time}")

    defaults = {
        "prompt_folder": prompt_folder,
        "image_count": str(image_count),
        "status": status,
        "model": model.strip() or "gpt-4o-mini",
        "with_image": str(with_image),
        "image_source": image_source,
        "submit_search": str(submit_search),
        "sitemap_url": sitemap_url.strip(),
        "openai_api_key": openai_api_key.strip(),
        "wp_domain": wp_domain.strip(),
        "wp_user": wp_user.strip(),
        "wp_app_password": wp_app_password.strip(),
        "pixabay_api_key": pixabay_api_key.strip(),
    }

    if run_now:
        if not topic.strip():
            st.error("Topic is required.")
            return
        if not prompt_folder:
            st.error("Prompt folder is required.")
            return
        try:
            config = build_config_from_inputs(
                topic=topic.strip(),
                main_topic=(main_topic.strip() or topic.strip()),
                sub_topics=sub_topics.strip(),
                prompt_folder=prompt_folder,
                image_count=image_count,
                status=defaults["status"],
                model=defaults["model"],
                with_image=with_image,
                image_source=defaults["image_source"],
                openai_api_key=defaults["openai_api_key"],
                wp_domain=defaults["wp_domain"],
                wp_user=defaults["wp_user"],
                wp_app_password=defaults["wp_app_password"],
                pixabay_api_key=defaults["pixabay_api_key"],
                submit_search=submit_search,
                sitemap_url=sitemap_url.strip(),
            )
            with st.spinner("Publishing..."):
                result = publish_post(config)
            render_result(result, with_image=config.with_image, status=config.status)
        except Exception as exc:
            st.error(f"Failed: {exc}")

    if schedule_one:
        if not topic.strip():
            st.error("Topic is required.")
            return
        if not prompt_folder:
            st.error("Prompt folder is required.")
            return
        try:
            config = build_config_from_inputs(
                topic=topic.strip(),
                main_topic=(main_topic.strip() or topic.strip()),
                sub_topics=sub_topics.strip(),
                prompt_folder=prompt_folder,
                image_count=image_count,
                status=defaults["status"],
                model=defaults["model"],
                with_image=with_image,
                image_source=defaults["image_source"],
                openai_api_key=defaults["openai_api_key"],
                wp_domain=defaults["wp_domain"],
                wp_user=defaults["wp_user"],
                wp_app_password=defaults["wp_app_password"],
                pixabay_api_key=defaults["pixabay_api_key"],
                submit_search=submit_search,
                sitemap_url=sitemap_url.strip(),
            )
            run_at = datetime.combine(run_date, run_time)
            job_id = schedule_single_job(scheduler, config, run_at)
            st.success(f"Scheduled: {job_id} at {run_at}")
        except Exception as exc:
            st.error(f"Schedule failed: {exc}")

    if schedule_bulk:
        if uploaded_file is None:
            st.error("CSV 또는 Excel 파일을 업로드해주세요.")
            return
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
            st.error(f"Bulk schedule failed: {exc}")


if __name__ == "__main__":
    main()
