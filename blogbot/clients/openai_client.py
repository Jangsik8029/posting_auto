import json
import re
from pathlib import Path

import requests

from blogbot.models import Article
from blogbot.utils import extract_json_object

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
    return "\\n".join(f"- {x['title']}: {x['url']}" for x in references)


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
    title = ""
    excerpt = ""
    seo_keyword = main_topic
    content_parts: list[str] = []

    for i, fp in enumerate(txt_files):
        prompt_text = _read_text_with_fallback(fp).strip()
        if not prompt_text:
            continue

        is_first = len(content_parts) == 0

        if is_first:
            system_prompt = (
                "You are an expert Korean blog writer. Follow the instruction below exactly. Do not mention AI. Keep claims realistic.\n\n"
                "Output format: Return ONLY valid JSON with keys: title, excerpt, content_html, seo_keyword. content_html must be valid HTML (this is the first segment of the article)."
            )
            user_prompt = (
                f"Main topic: {main_topic}\n"
                f"Sub topics: {sub_topics_text}\n"
                "Write in Korean. Use references when provided.\n\n"
                f"References:\n{refs_text}\n\n"
                "--- Instruction for this segment ---\n\n"
                f"{prompt_text}"
            )
        else:
            system_prompt = (
                "You are an expert Korean blog writer. You are continuing an article. Follow the instruction below. Output ONLY valid JSON with one key: content_html (valid HTML segment to append). Do not repeat the previous content; write only the next segment."
            )
            user_prompt = (
                "--- So far (do not repeat, just continue after this) ---\n\n"
                f"{''.join(content_parts)}\n\n"
                "--- Instruction for the next segment ---\n\n"
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

    return Article(
        title=title,
        excerpt=excerpt,
        content_html="\n".join(content_parts),
        seo_keyword=seo_keyword,
    )
