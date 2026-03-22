import json
import logging
import re
from pathlib import Path

import pandas as pd
import requests

from blogbot.models import Article
from blogbot.utils import extract_json_object

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
PROMPT_ROOT = Path(__file__).resolve().parent.parent / "prompt"


def list_prompt_folders() -> list[str]:
    """prompt 하위 폴더 이름 목록 (선택용)."""
    if not PROMPT_ROOT.exists():
        return []
    return sorted(
        [d.name for d in PROMPT_ROOT.iterdir() if d.is_dir()],
        key=str.lower,
    )


def _format_refs(references: list[dict[str, str]]) -> str:
    if not references:
        return "- (none)"
    return "\n".join(f"- {x['title']}: {x['url']}" for x in references)


COMMON_WRITING_RULES = """## 페르소나
너는 직접 발품 팔아 정보를 모으고 정리하는 경험 많은 한국 블로거야.
독자에게 친구가 알려주듯 따뜻하고 편안하게 설명하는 스타일이야.

## 문체 규칙
- 딱딱한 보도문이 아니라, 직접 알아보고 정리해주는 느낌의 자연스러운 존댓말 블로그체로 작성
- "저도 처음엔 헷갈렸는데요", "이 부분이 가장 중요합니다", "꼭 확인해 보세요" 같은 자연스러운 연결 문장을 중간중간 삽입
- 초보자도 바로 이해할 수 있게 쉽게 풀어서 설명
- 과장 없이 현실적으로 서술
- 공백 포함 150자 내외마다 마침표(.) 기준으로 문단을 나눠서 가독성 확보
- 전체 본문은 2,000자 이상 작성
- AI가 쓴 티가 절대 나지 않게 작성
- "이 글을 작성했습니다", "포스트를 작성했습니다" 같은 메타 코멘트는 절대 넣지 않기

## HTML 규칙
- 주어진 HTML 템플릿의 태그 구조와 서식을 그대로 유지하고, "내용 N자 내외 작성" 부분만 실제 내용으로 교체
- 버튼(<a class="click-me-button">)은 템플릿에 있는 것만 사용하고, 추가 버튼을 절대 생성하지 않기
- ```html, ``` 같은 코드 마커는 절대 포함하지 않기
- 내용이 없는 빈 항목은 삭제

## 데이터 활용 규칙
- "참고 데이터"가 제공되면 실제 수치와 지역명을 글에 정확하게 반영
- 데이터의 숫자를 임의로 변경하지 않고, 표나 본문에 그대로 활용
- 주제와 관련된 지역 데이터를 우선적으로 활용하되, 다른 지역과 비교하면 더 유용한 글이 됨

## SEO 규칙
- 프롬프트에서 제시한 검색 키워드를 본문 전체에 자연스럽게 분산 배치
- 소제목(h2, h3)을 활용해 가독성과 검색 최적화를 동시에 확보
- 글 말미에 핵심 내용을 간결하게 요약

## 네이버 검색엔진 최적화(SEO) 규칙
- **title(제목)**: 페이지 주제를 나타내는 정확하고 고유한 제목. 한 글당 하나의 제목만, 25~55자 내외(한글 기준). 너무 길지 않게 작성.
- **excerpt(요약)**: meta description으로 사용됨. 검색 결과 스니펫에 노출되므로, 페이지 내용을 2~3문장으로 고유하게 요약. 120~155자 내외. 다른 글과 동일한 문구 사용 금지.
- **본문 HTML 구조**: 본문에는 <h1>을 사용하지 말고 <h2>, <h3>만 사용. (사이트가 글 제목을 H1으로 노출하므로, 본문에 H1이 있으면 H1이 2개 이상 되어 검색로봇에 불리함.)
- **이미지**: 본문에 img를 넣을 경우 반드시 alt 속성에 해당 이미지 내용을 설명하는 텍스트를 넣기. alt 누락 시 검색로봇이 이미지를 해석하기 어려움."""


def _build_first_system_prompt() -> str:
    return (
        f"{COMMON_WRITING_RULES}\n\n"
        "## 출력 형식\n"
        "반드시 유효한 JSON만 반환. 키: title, excerpt, content_html, seo_keyword\n"
        "- title: 이 글만의 고유·정확한 제목 1개, 25~55자 내외(한글).\n"
        "- excerpt: meta description용, 검색 스니펫에 쓰일 고유 요약 2~3문장, 120~155자 내외.\n"
        "- content_html: 유효한 HTML(첫 번째 섹션). 본문에는 h2, h3만 사용하고 h1은 사용하지 않기. img 사용 시 반드시 alt 속성 포함."
    )


def _build_continuation_system_prompt() -> str:
    return (
        f"{COMMON_WRITING_RULES}\n\n"
        "## 추가 규칙 (이어쓰기)\n"
        "- 이전 섹션의 내용을 반복하지 않고, 자연스럽게 이어서 작성\n"
        "- 톤과 문체를 이전 섹션과 일관되게 유지\n"
        "- content_html에는 h2, h3만 사용(h1 사용 금지). img 사용 시 반드시 alt 속성 포함\n\n"
        "## 출력 형식\n"
        "반드시 유효한 JSON만 반환. 키: content_html (이어붙일 HTML 섹션)"
    )


DATA_EXTENSIONS = ("*.csv", "*.xlsx", "*.ods")


def _load_data_files(prompt_dir: Path, topic: str = "") -> str:
    """프롬프트 폴더에 있는 데이터 파일(csv/xlsx/ods)을 텍스트로 변환해 반환."""
    parts: list[str] = []
    for pattern in DATA_EXTENSIONS:
        for fp in sorted(prompt_dir.glob(pattern)):
            try:
                if fp.suffix == ".csv":
                    df = pd.read_csv(fp)
                elif fp.suffix == ".ods":
                    df = pd.read_excel(fp, engine="odf")
                else:
                    df = pd.read_excel(fp)
            except Exception as exc:
                logger.warning("데이터 파일 로드 실패 %s: %s", fp.name, exc)
                continue

            if df.empty:
                continue

            # NaN/빈칸을 '-'로 채워서 화물·승합 등 null이 '-'로 전달되도록 함
            df_display = df.fillna("-")

            # 파이프 구분자로 출력해 열이 명확히 구분되도록 함 (화물·승합 값이 공백에 묻히지 않음)
            def _format_table(inner: pd.DataFrame) -> str:
                return inner.to_csv(sep="|", index=False, encoding="utf-8").strip()

            filtered = _filter_data_by_topic(df_display, topic)
            if filtered is not None and not filtered.empty:
                text = _format_table(filtered)
                parts.append(f"[데이터: {fp.name} — 주제 관련 {len(filtered)}건]\n{text}")

                remaining = df_display[~df_display.index.isin(filtered.index)]
                if not remaining.empty:
                    summary = _format_table(remaining)
                    parts.append(f"[데이터: {fp.name} — 기타 지역 {len(remaining)}건]\n{summary}")
            else:
                text = _format_table(df_display)
                parts.append(f"[데이터: {fp.name} — 전체 {len(df_display)}건]\n{text}")

    return "\n\n".join(parts)


def _filter_data_by_topic(df: pd.DataFrame, topic: str) -> pd.DataFrame | None:
    """주제(topic)에서 지역명을 추출해 데이터를 필터링."""
    if not topic:
        return None

    text_cols = [c for c in df.columns if df[c].dtype == object]
    if not text_cols:
        return None

    masks = []
    for col in text_cols[:2]:
        col_values = df[col].astype(str)
        mask = col_values.apply(lambda v: v in topic or topic.find(v) >= 0)
        masks.append(mask)

    combined = masks[0]
    for m in masks[1:]:
        combined = combined | m

    matched = df[combined]
    return matched if len(matched) > 0 else None


def _read_text_with_fallback(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _natural_sort_key(path: Path) -> list[int | str]:
    """파일명의 숫자를 기준으로 정렬해 1.txt, 2.txt, 5.txt 순서 보장."""
    parts = re.split(r"(\d+)", path.stem)
    return [int(x) if x.isdigit() else x for x in parts if x]


def _get_ordered_txt_files(prompt_dir: Path) -> list[Path]:
    """하위 폴더 내 txt 파일을 글 순서(1, 2, 3...)대로 반환."""
    return sorted(
        [p for p in prompt_dir.glob("*.txt") if p.is_file()],
        key=lambda p: (_natural_sort_key(p), p.name),
    )


def _call_chatgpt(
    messages: list[dict[str, str]],
    api_key: str,
    model: str,
) -> str:
    payload = {
        "model": model,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        OPENAI_API_URL,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=120,
    )
    if response.status_code != 200:
        raise RuntimeError(f"OpenAI API failed ({response.status_code}): {response.text[:300]}")
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response shape: {data}") from exc


def generate_article_with_chatgpt(
    main_topic: str,
    sub_topics: list[str],
    prompt_folder: str,
    references: list[dict[str, str]],
    api_key: str,
    model: str,
) -> Article:
    """폴더 내 각 txt 파일마다 한 번씩 프롬프트하여 나온 글을 순서대로 연결한 최종 글을 반환."""
    if not prompt_folder.strip():
        raise RuntimeError("prompt_folder is required. Choose a folder under blogbot/prompt/.")

    prompt_dir = PROMPT_ROOT / prompt_folder.strip()
    if not prompt_dir.is_dir():
        raise RuntimeError(f"Prompt folder not found: {prompt_dir}")

    txt_files = _get_ordered_txt_files(prompt_dir)
    if not txt_files:
        raise RuntimeError(f"No .txt files found in prompt folder: {prompt_folder}")

    sub_topics_text = ", ".join(sub_topics) if sub_topics else "(none)"
    refs_text = _format_refs(references)
    data_text = _load_data_files(prompt_dir, main_topic)
    title = ""
    excerpt = ""
    seo_keyword = main_topic
    content_parts: list[str] = []

    for i, fp in enumerate(txt_files):
        prompt_text = _read_text_with_fallback(fp).strip()
        if not prompt_text:
            continue

        is_first = len(content_parts) == 0

        data_block = ""
        if data_text:
            data_block = f"\n\n--- 참고 데이터 (실제 수치를 글에 반영) ---\n\n{data_text}"

        if is_first:
            system_prompt = _build_first_system_prompt()
            user_prompt = (
                f"주제: {main_topic}\n"
                f"세부 주제: {sub_topics_text}\n"
                f"참고자료:\n{refs_text}"
                f"{data_block}\n\n"
                "--- 이 섹션의 작성 지시 ---\n\n"
                f"{prompt_text}"
            )
        else:
            system_prompt = _build_continuation_system_prompt()
            last_part = content_parts[-1]
            if len(last_part) > 1500:
                last_part = last_part[-1500:]
            user_prompt = (
                f"주제: {main_topic}"
                f"{data_block}\n\n"
                "--- 직전 섹션 (반복 금지, 흐름 참고용) ---\n\n"
                f"{last_part}\n\n"
                "--- 이 섹션의 작성 지시 ---\n\n"
                f"{prompt_text}"
            )

        raw = _call_chatgpt(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            api_key=api_key,
            model=model,
        )
        seg = extract_json_object(raw)

        if is_first:
            title = str(seg.get("title", "")).strip()
            excerpt = str(seg.get("excerpt", "")).strip()
            seo_keyword = str(seg.get("seo_keyword", main_topic)).strip()

        part = str(seg.get("content_html", "")).strip()
        if part:
            content_parts.append(part)

    if not content_parts:
        raise RuntimeError("No content was generated from the prompt files.")

    if not title:
        title = main_topic
    if not excerpt:
        excerpt = title

    # 네이버 SEO: 본문에 H1이 있으면 H1 중복이 되므로 본문은 H2/H3만 사용
    content_html = "\n".join(content_parts)
    content_html = content_html.replace("<h1 ", "<h2 ").replace("</h1>", "</h2>")

    # 네이버 SEO 권장: title 25~55자, meta description 120~155자
    if len(title) > 55:
        title = title[:54] + "…" if len(title) > 54 else title
    if len(excerpt) > 155:
        excerpt = excerpt[:154] + "…" if len(excerpt) > 154 else excerpt

    return Article(
        title=title,
        excerpt=excerpt,
        content_html=content_html,
        seo_keyword=seo_keyword,
    )
