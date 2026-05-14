"""카페 크롤링 → 토픽 선정 → 자동 발행 파이프라인 UI.

검색어 입력 / DataLab 트렌드 / 프롬프트 폴더 기반 자동 수집
→ 토픽 선정 → 프롬프트 자동 생성 → 이미지 자동 포함 → 발행까지 원클릭 처리.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta

import streamlit as st

from blogbot.clients.openai_client import list_prompt_folders
from blogbot.config import AppConfig, ConfigValidationError
from blogbot.workflows.publish import publish_post_auto

from ui_views.config_builder import build_config_from_inputs
from ui_views.inputs import InputValues
from ui_views.scheduler import get_scheduler

logger = logging.getLogger(__name__)


def _job_publish_auto(config_dict: dict) -> None:
    from blogbot.config import AppConfig
    from blogbot.workflows.publish import publish_post_auto as _pub
    config = AppConfig(**config_dict)
    _pub(config)


def _load_dotenv_once() -> None:
    if not getattr(_load_dotenv_once, "_done", False):
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        except ImportError:
            pass
        _load_dotenv_once._done = True


def _crawl_naver(query: str) -> list[dict]:
    from cafe_crawler.collectors.naver import search_naver_cafe
    return list(search_naver_cafe(query, sort="date"))


def _score_posts(posts: list[dict]) -> list[dict]:
    from cafe_crawler.analyzer.ranker import score_posts
    return score_posts(posts)


def _save_to_db(query: str, scored: list[dict]) -> int:
    from cafe_crawler.storage.db import create_search, save_posts
    search_id = create_search(query)
    save_posts(search_id, scored)
    return search_id


def _select_topics(search_id: int, top: int = 5):
    from cafe_crawler.workflows.topic_selector import select_topics
    return select_topics(search_id, top=top)


def _fetch_datalab_trends(seed_groups=None, top_n=5):
    from cafe_crawler.collectors.datalab import fetch_trending_keywords
    return fetch_trending_keywords(seed_groups=seed_groups, top_n=top_n)


def _build_auto_config(values: InputValues, topic: str, sub_topics: str) -> AppConfig:
    return build_config_from_inputs(
        topic=topic,
        main_topic=topic,
        sub_topics=sub_topics,
        prompt_folder=values.prompt_folder or "",
        image_count=values.image_count,
        status=values.status,
        model=values.model.strip() or "gpt-4o-mini",
        with_image=True,
        image_source="title",
        openai_api_key=values.openai_api_key.strip(),
        wp_domain=values.wp_domain.strip(),
        wp_user=values.wp_user.strip(),
        wp_app_password=values.wp_app_password.strip(),
        pixabay_api_key=values.pixabay_api_key.strip(),
        submit_search=values.submit_search,
        sitemap_url=values.sitemap_url.strip(),
    )


def _validate_auto_config(config: AppConfig) -> None:
    missing: list[str] = []
    if not config.topic.strip():
        missing.append("topic")
    if not config.openai_api_key.strip():
        missing.append("openai_api_key")
    if not config.wp_domain.strip():
        missing.append("wp_domain")
    if not config.wp_user.strip():
        missing.append("wp_user")
    if not config.wp_app_password.strip():
        missing.append("wp_app_password")
    if missing:
        raise ConfigValidationError(f"필수 값 누락: {', '.join(missing)}")


def _schedule_auto_job(scheduler, config: AppConfig, run_at: datetime) -> str:
    from apscheduler.triggers.date import DateTrigger
    job_id = f"auto-{int(run_at.timestamp())}-{abs(hash(config.topic)) % 10000}"
    scheduler.add_job(
        _job_publish_auto,
        trigger=DateTrigger(run_date=run_at),
        args=[asdict(config)],
        id=job_id,
        replace_existing=True,
    )
    return job_id


def render_cafe_pipeline(values: InputValues) -> None:
    """카페 크롤링 자동 발행 파이프라인."""
    _load_dotenv_once()

    st.markdown("---")
    st.subheader("자동 발행 파이프라인")
    st.caption(
        "검색어 입력 / DataLab 인기 트렌드 / 프롬프트 폴더 기반 → "
        "토픽 선정 → 프롬프트 자동 생성 → 이미지 자동 포함 → 발행"
    )

    # ── 1. 검색어 소스 선택 ──
    source = st.radio(
        "검색어 소스",
        ["직접 입력", "네이버 DataLab 인기 트렌드", "프롬프트 폴더 주제"],
        horizontal=True,
        key="cafe_source",
    )

    queries: list[str] = []

    if source == "직접 입력":
        raw = st.text_area(
            "검색어 (줄바꿈으로 여러 개 입력 가능)",
            placeholder="아이와 가볼만한 곳\n전기차 보조금 2026\n제철 해산물",
            height=100,
            key="cafe_queries_input",
        )
        queries = [q.strip() for q in raw.strip().splitlines() if q.strip()]

    elif source == "네이버 DataLab 인기 트렌드":
        _render_datalab_section()
        if "datalab_queries" in st.session_state:
            queries = st.session_state.datalab_queries

    else:
        folders = list_prompt_folders()
        if folders:
            selected_folders = st.multiselect(
                "수집할 주제 폴더 선택",
                options=folders,
                default=folders[:3] if len(folders) >= 3 else folders,
                key="cafe_folder_select",
            )
            queries = selected_folders
        else:
            st.warning("blogbot/prompt/ 에 프롬프트 폴더가 없습니다.")

    # ── 2. 발행 옵션 ──
    col1, col2, col3 = st.columns(3)
    with col1:
        top_n = st.number_input("검색어당 토픽 수", min_value=1, max_value=5, value=1, key="cafe_top_n")
    with col2:
        publish_mode = st.selectbox(
            "발행 방식",
            ["즉시 발행", "예약 발행"],
            key="cafe_publish_mode",
        )
    with col3:
        if publish_mode == "예약 발행":
            interval = st.number_input("발행 간격 (분)", min_value=5, max_value=1440, value=60, key="cafe_interval")
        else:
            interval = 0

    if publish_mode == "예약 발행":
        col_d, col_t = st.columns(2)
        start_dt = datetime.now() + timedelta(minutes=10)
        with col_d:
            s_date = st.date_input("시작 날짜", value=start_dt.date(), key="cafe_s_date")
        with col_t:
            s_time = st.time_input("시작 시간", value=start_dt.time(), key="cafe_s_time")
        start_dt = datetime.combine(s_date, s_time)
    else:
        start_dt = datetime.now()

    # ── 3. 미리보기 ──
    if queries:
        st.info(
            f"검색어 {len(queries)}개 x 토픽 {top_n}개 = 최대 **{len(queries) * int(top_n)}건** 발행\n\n"
            f"프롬프트: 토픽에 맞게 **자동 생성** | 이미지: 제목 썸네일 **자동 포함**"
        )

    # ── 4. 실행 버튼 ──
    run_btn = st.button(
        f"크롤링 → 자동 {'발행' if publish_mode == '즉시 발행' else '예약'} 시작",
        type="primary",
        key="cafe_run_btn",
        disabled=not queries,
    )

    if run_btn:
        _execute_pipeline(
            queries=queries,
            top_n=int(top_n),
            values=values,
            publish_mode=publish_mode,
            start_dt=start_dt,
            interval_minutes=int(interval),
        )


def _render_datalab_section() -> None:
    """DataLab 트렌드 조회 UI."""
    from cafe_crawler.collectors.datalab import DEFAULT_SEED_KEYWORDS, build_seed_from_custom

    st.markdown("#### 네이버 DataLab 인기 트렌드")

    seed_mode = st.radio(
        "시드 키워드",
        ["기본 카테고리 (10개 분야)", "직접 입력"],
        horizontal=True,
        key="datalab_seed_mode",
    )

    seed_groups = None
    if seed_mode == "직접 입력":
        custom_raw = st.text_area(
            "시드 키워드 (줄바꿈으로 구분)",
            placeholder="아이와 가볼만한 곳\n전기차 보조금\n제철 해산물\n국내 여행",
            height=80,
            key="datalab_custom_seeds",
        )
        custom_list = [q.strip() for q in custom_raw.strip().splitlines() if q.strip()]
        if custom_list:
            seed_groups = build_seed_from_custom(custom_list)
    else:
        st.caption(
            "분야: " + ", ".join(g["groupName"] for g in DEFAULT_SEED_KEYWORDS)
        )

    col_count, col_days = st.columns(2)
    with col_count:
        trend_top_n = st.number_input("상위 몇 개?", min_value=1, max_value=10, value=5, key="datalab_top_n")
    with col_days:
        trend_days = st.number_input("조회 기간 (일)", min_value=7, max_value=90, value=30, key="datalab_days")

    fetch_btn = st.button("트렌드 조회", key="datalab_fetch_btn")

    if fetch_btn:
        with st.spinner("네이버 DataLab 트렌드 조회 중..."):
            try:
                results = _fetch_datalab_trends(
                    seed_groups=seed_groups,
                    top_n=int(trend_top_n),
                )
            except RuntimeError as e:
                st.error(f"DataLab 조회 실패: {e}")
                return

        if not results:
            st.warning("트렌드 결과가 없습니다.")
            return

        # 결과 표시
        st.markdown("**조회 결과 (상승률 순)**")
        selected_keywords: list[str] = []
        for i, r in enumerate(results):
            trend_icon = "🔥" if r["trend_score"] > 1.2 else "📈" if r["trend_score"] > 1.0 else "📉"
            checked = st.checkbox(
                f"{trend_icon} **{r['group_name']}** — "
                f"상승률 {r['trend_score']:.1f}x | 검색량 {r['avg_volume']:.0f}",
                value=r["trend_score"] >= 1.0,
                key=f"datalab_sel_{i}",
            )
            if checked:
                selected_keywords.append(r["best_keyword"])

        st.session_state.datalab_queries = selected_keywords
        if selected_keywords:
            st.success(f"선택된 검색어 {len(selected_keywords)}개: {', '.join(selected_keywords)}")

    # 이전 조회 결과가 세션에 있으면 표시
    if "datalab_queries" in st.session_state and st.session_state.datalab_queries:
        st.caption(f"현재 선택: {', '.join(st.session_state.datalab_queries)}")


def _execute_pipeline(
    queries: list[str],
    top_n: int,
    values: InputValues,
    publish_mode: str,
    start_dt: datetime,
    interval_minutes: int,
) -> None:
    """전체 파이프라인 실행: 크롤링 → 토픽 → 자동 글 생성 → 발행/예약."""
    scheduler = get_scheduler()
    total_success = 0
    total_errors: list[str] = []
    job_index = 0
    progress = st.progress(0, text="준비 중...")

    for qi, query in enumerate(queries):
        progress.progress(
            qi / len(queries),
            text=f"[{qi + 1}/{len(queries)}] '{query}' 크롤링 중...",
        )

        # 크롤링
        try:
            posts = _crawl_naver(query)
        except RuntimeError as e:
            total_errors.append(f"'{query}' 크롤링 실패: {e}")
            continue

        if not posts:
            total_errors.append(f"'{query}' 수집된 게시글 없음")
            continue

        st.caption(f"'{query}' → {len(posts)}건 수집")

        # 점수 + DB 저장
        scored = _score_posts(posts)
        search_id = _save_to_db(query, scored)

        # 토픽 선정
        try:
            candidates = _select_topics(search_id, top=top_n)
        except Exception as e:
            total_errors.append(f"'{query}' 토픽 추출 실패: {e}")
            continue

        if not candidates:
            total_errors.append(f"'{query}' 토픽 후보 없음")
            continue

        # 각 토픽 자동 발행/예약
        for c in candidates:
            sub_str = ", ".join(c.sub_topics[:5])
            try:
                config = _build_auto_config(values, c.main_topic, sub_str)
                _validate_auto_config(config)
            except (ConfigValidationError, RuntimeError) as e:
                total_errors.append(f"'{c.main_topic}' 설정 오류: {e}")
                continue

            if publish_mode == "즉시 발행":
                try:
                    progress.progress(
                        qi / len(queries),
                        text=f"'{c.main_topic}' 글 생성 & 발행 중...",
                    )
                    result = publish_post_auto(config)
                    st.success(
                        f"발행 완료: **{c.main_topic}** → "
                        f"Post #{result['post_id']} | {result['title']}"
                    )
                    if result.get("public_url"):
                        st.link_button("글 보기", result["public_url"])
                    total_success += 1
                except Exception as e:
                    logger.exception(f"Auto publish failed: {c.main_topic}")
                    total_errors.append(f"'{c.main_topic}' 발행 실패: {e}")
            else:
                run_at = start_dt + timedelta(minutes=interval_minutes * job_index)
                try:
                    job_id = _schedule_auto_job(scheduler, config, run_at)
                    st.success(
                        f"예약: **{c.main_topic}** → "
                        f"{run_at.strftime('%Y-%m-%d %H:%M')} ({job_id})"
                    )
                    total_success += 1
                except Exception as e:
                    logger.exception(f"Schedule failed: {c.main_topic}")
                    total_errors.append(f"'{c.main_topic}' 예약 실패: {e}")

            job_index += 1

    progress.progress(1.0, text="완료!")

    # 결과 요약
    st.markdown("---")
    if total_success:
        action = "발행" if publish_mode == "즉시 발행" else "예약"
        st.success(f"총 **{total_success}건** {action} 완료")
    if total_errors:
        with st.expander(f"오류 {len(total_errors)}건", expanded=False):
            for err in total_errors:
                st.error(err)
    if total_success and not total_errors:
        st.balloons()
