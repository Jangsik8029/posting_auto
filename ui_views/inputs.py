"""주제·프롬프트·이미지·연결 설정 입력 UI."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import streamlit as st

from blogbot.clients.openai_client import list_prompt_folders

from ui_views.settings import save_ui_settings


@dataclass
class InputValues:
    topic: str
    main_topic: str
    sub_topics: str
    prompt_folder: str
    image_count: int
    status: str
    model: str
    with_image: bool
    image_source: str
    submit_search: bool
    sitemap_url: str
    openai_api_key: str
    wp_domain: str
    wp_user: str
    wp_app_password: str
    pixabay_api_key: str


_IMAGE_SOURCE_LABELS = {
    "local": "로컬 (프롬프트 폴더)",
    "title": "제목 썸네일 (자동 생성, 무료)",
    "dalle": "DALL-E (AI 생성, 유료)",
    "pixabay": "Pixabay (스톡 검색)",
}
_IMAGE_SOURCE_OPTIONS = ["local", "title", "dalle", "pixabay"]
_STATUS_OPTIONS = ["draft", "publish", "private"]


def render_inputs_panel(saved: dict[str, Any]) -> InputValues:
    """좌측 입력 컬럼을 그리고 값을 반환한다."""
    topic = st.text_input(
        "Topic",
        placeholder="e.g. 5-year-old weekend play ideas",
        value=saved.get("topic", ""),
    )
    main_topic = st.text_input("Main topic", value=saved.get("main_topic", ""))
    sub_topics = st.text_input("Sub topics (comma-separated)", value=saved.get("sub_topics", ""))

    prompt_folders = list_prompt_folders()
    if not prompt_folders:
        st.warning("No prompt folders found under blogbot/prompt/. Add a subfolder with .txt files.")
    pf_saved = saved.get("prompt_folder", "")
    pf_index = prompt_folders.index(pf_saved) if prompt_folders and pf_saved in prompt_folders else 0
    prompt_folder = (
        st.selectbox("Prompt folder (글 작성 가이드)", options=prompt_folders, index=pf_index)
        if prompt_folders
        else ""
    )

    ic_saved = int(saved.get("image_count", 4))
    image_count = st.slider("Image count", min_value=1, max_value=5, value=min(max(ic_saved, 1), 5))

    status_saved = saved.get("status", "draft")
    status_index = _STATUS_OPTIONS.index(status_saved) if status_saved in _STATUS_OPTIONS else 0
    status = st.selectbox("Post status", _STATUS_OPTIONS, index=status_index)
    model = st.text_input("OpenAI model", value=saved.get("model", "gpt-4o-mini"))

    with_image = st.checkbox("이미지 포함", value=bool(saved.get("with_image", True)))
    is_saved = saved.get("image_source", "local")
    is_index = _IMAGE_SOURCE_OPTIONS.index(is_saved) if is_saved in _IMAGE_SOURCE_OPTIONS else 0
    image_source = st.radio(
        "이미지 소스",
        options=_IMAGE_SOURCE_OPTIONS,
        format_func=lambda x: _IMAGE_SOURCE_LABELS[x],
        index=is_index,
        horizontal=True,
    )

    submit_search = st.checkbox(
        "Submit sitemap to search engines", value=bool(saved.get("submit_search", False))
    )
    sitemap_url = st.text_input("Sitemap URL (optional)", value=saved.get("sitemap_url", ""))

    openai_api_key, wp_domain, wp_user, wp_app_password, pixabay_api_key = _render_connection_expander(
        topic=topic,
        main_topic=main_topic,
        sub_topics=sub_topics,
        prompt_folder=prompt_folder,
        image_count=image_count,
        status=status,
        model=model,
        with_image=with_image,
        image_source=image_source,
        submit_search=submit_search,
        sitemap_url=sitemap_url,
    )

    return InputValues(
        topic=topic,
        main_topic=main_topic,
        sub_topics=sub_topics,
        prompt_folder=prompt_folder,
        image_count=image_count,
        status=status,
        model=model,
        with_image=with_image,
        image_source=image_source,
        submit_search=submit_search,
        sitemap_url=sitemap_url,
        openai_api_key=openai_api_key,
        wp_domain=wp_domain,
        wp_user=wp_user,
        wp_app_password=wp_app_password,
        pixabay_api_key=pixabay_api_key,
    )


def _render_connection_expander(**current: Any) -> tuple[str, str, str, str, str]:
    with st.expander("Connection settings", expanded=False):
        st.caption("API 키·비밀번호는 저장되지 않습니다. 필요 시 환경 변수(.env) 또는 매번 입력을 사용하세요.")
        openai_api_key = st.text_input(
            "OpenAI API Key", value=os.environ.get("OPENAI_API_KEY", ""), type="password"
        )
        wp_domain = st.text_input("WordPress Domain", value=os.environ.get("WP_DOMAIN", ""))
        wp_user = st.text_input("WordPress User", value=os.environ.get("WP_USER", ""))
        wp_app_password = st.text_input(
            "WordPress App Password",
            value=os.environ.get("WP_APP_PASSWORD", ""),
            type="password",
        )
        pixabay_api_key = st.text_input(
            "Pixabay API Key", value=os.environ.get("PIXABAY_API_KEY", ""), type="password"
        )
        if st.button("현재 설정 저장 (다음부터 자동 불러옴)"):
            save_ui_settings(current)
            st.success("저장되었습니다. 시크릿(API 키·비밀번호)은 저장되지 않습니다.")
    return openai_api_key, wp_domain, wp_user, wp_app_password, pixabay_api_key
