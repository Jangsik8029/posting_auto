import logging
from dataclasses import dataclass
from pathlib import Path

from blogbot.clients.dalle_client import generate_images_with_dalle, load_local_images, save_dalle_image_locally
from blogbot.clients.openai_client import PROMPT_ROOT, generate_article_with_chatgpt
from blogbot.clients.pixabay_client import download_images_with_pixabay, save_image_locally
from blogbot.clients.thumbnail_gen import save_title_thumbnail
from blogbot.clients.wordpress_client import (
    choose_public_url,
    post_to_wordpress,
    set_featured_media,
    upload_media_xmlrpc,
)
from blogbot.config import AppConfig
from blogbot.integrations.knowledge_db import search_knowledge
from blogbot.integrations.scraper import collect_reference_material
from blogbot.integrations.search_submitter import submit_post_to_search_sites
from blogbot.models import Article, PublishResult

logger = logging.getLogger(__name__)


@dataclass
class _UploadOutcome:
    wp_url: str
    attachment_id: int | None
    error_message: str


def _inject_images_into_content(content_html: str, title: str, image_urls: list[str]) -> str:
    """이미지를 본문에 삽입. alt는 네이버 SEO를 위해 제목·순서 기반 설명으로 설정."""
    if not image_urls:
        return content_html

    def _alt(i: int) -> str:
        return f"{title} 대표 이미지" if i == 0 else f"{title} 관련 이미지 {i + 1}"

    if "<h2" not in content_html:
        blocks = [f'<p><img src="{u}" alt="{_alt(i)}" /></p>' for i, u in enumerate(image_urls)]
        return "\n".join(blocks) + "\n" + content_html

    parts = content_html.split("<h2")
    rebuilt = parts[0]
    image_idx = 0

    if image_idx < len(image_urls):
        rebuilt = f'<p><img src="{image_urls[image_idx]}" alt="{_alt(image_idx)}" /></p>\n' + rebuilt
        image_idx += 1

    for p in parts[1:]:
        if image_idx < len(image_urls):
            rebuilt += f'\n<p><img src="{image_urls[image_idx]}" alt="{_alt(image_idx)}" /></p>\n'
            image_idx += 1
        rebuilt += "<h2" + p

    while image_idx < len(image_urls):
        rebuilt += f'\n<p><img src="{image_urls[image_idx]}" alt="{_alt(image_idx)}" /></p>\n'
        image_idx += 1
    return rebuilt


def _resolve_image_label(config: AppConfig, query: str = "") -> str:
    """이미지 검색/생성에 쓰일 레이블을 결정한다."""
    return (query.strip() or config.topic).strip()


def _upload_single_image(config: AppConfig, image_path: Path) -> _UploadOutcome:
    """이미지 한 장을 WP에 업로드한다. 오류 메시지·URL·첨부 ID를 담은 객체를 반환."""
    try:
        media = upload_media_xmlrpc(
            domain=config.wp_domain,
            wp_user=config.wp_user,
            wp_app_password=config.wp_app_password,
            file_path=image_path,
        )
    except RuntimeError as exc:
        if "413" not in str(exc):
            raise
        logger.warning("Image too large (HTTP 413): %s", image_path.name)
        return _UploadOutcome(wp_url="", attachment_id=None, error_message=str(exc))

    wp_url = str(media.get("url", "")).strip()
    attachment_id_raw = media.get("id")
    try:
        attachment_id = int(attachment_id_raw) if attachment_id_raw is not None else None
    except (TypeError, ValueError):
        attachment_id = None
    return _UploadOutcome(wp_url=wp_url, attachment_id=attachment_id, error_message="")


def _upload_batch(
    config: AppConfig,
    jobs: list[tuple[Path, str]],
) -> tuple[list[str], list[str], list[int], str]:
    """(path, source_label) 목록을 차례로 업로드. (urls, sources, ids, last_error) 반환."""
    urls: list[str] = []
    sources: list[str] = []
    attachment_ids: list[int] = []
    last_error = ""
    for image_path, source_label in jobs:
        outcome = _upload_single_image(config, image_path)
        if outcome.error_message:
            last_error = outcome.error_message
        if outcome.wp_url:
            urls.append(outcome.wp_url)
            sources.append(source_label)
            if outcome.attachment_id is not None and not attachment_ids:
                attachment_ids.append(outcome.attachment_id)
    return urls, sources, attachment_ids, last_error


def publish_post(config: AppConfig) -> PublishResult:
    references = collect_reference_material(config.main_topic, config.sub_topics, max_links=5)
    if config.knowledge_keyword:
        db_refs = search_knowledge(config.knowledge_db_path, config.knowledge_keyword, limit=5)
        merged = references + [{"title": x["title"], "url": x["url"]} for x in db_refs]
        dedup: list[dict[str, str]] = []
        seen: set[str] = set()
        for ref in merged:
            url = ref["url"].strip()
            if not url or url in seen:
                continue
            seen.add(url)
            dedup.append(ref)
        references = dedup[:8]

    article: Article = generate_article_with_chatgpt(
        main_topic=config.main_topic,
        sub_topics=config.sub_topics,
        prompt_folder=config.prompt_folder,
        references=references,
        api_key=config.openai_api_key,
        model=config.model,
    )

    image_urls: list[str] = []
    image_sources: list[str] = []
    attachment_ids: list[int] = []
    image_status = "not_requested"
    image_message = ""

    if config.with_image:
        image_status = "requested"
        query = " ".join([config.main_topic, *config.sub_topics]).strip()
        label = _resolve_image_label(config, query)
        jobs: list[tuple[Path, str]] = []

        if config.image_source == "local":
            prompt_dir = PROMPT_ROOT / config.prompt_folder.strip()
            local_paths = load_local_images(prompt_dir, count=config.image_count)
            if not local_paths:
                image_status = "upload_skipped"
                image_message = "프롬프트 폴더에 이미지 파일이 없습니다."
            else:
                jobs = [(p, f"local:{p.name}") for p in local_paths]

        elif config.image_source == "title":
            for i in range(1, config.image_count + 1):
                path = save_title_thumbnail(label, index=i)
                jobs.append((path, f"title-gen:{path.name}"))

        elif config.image_source == "dalle":
            downloaded = generate_images_with_dalle(
                topic=label,
                api_key=config.openai_api_key,
                count=config.image_count,
            )
            for i, (image_bytes, source_url) in enumerate(downloaded, start=1):
                path = save_dalle_image_locally(image_bytes, label, index=i)
                jobs.append((path, source_url))

        else:  # pixabay
            downloaded = download_images_with_pixabay(query, config.pixabay_api_key, count=config.image_count)
            for i, (image_bytes, source_url) in enumerate(downloaded, start=1):
                path = save_image_locally(image_bytes, label, ext="jpg", index=i)
                jobs.append((path, source_url))

        if jobs:
            urls, sources, ids, last_err = _upload_batch(config, jobs)
            image_urls.extend(urls)
            image_sources.extend(sources)
            attachment_ids.extend(ids)
            if last_err and not image_message:
                image_message = last_err

        if image_urls:
            article.content_html = _inject_images_into_content(article.content_html, article.title, image_urls)
            image_status = "uploaded"
        elif image_status != "upload_skipped":
            image_status = "upload_skipped"

    first_attachment_id = attachment_ids[0] if attachment_ids else None

    created = post_to_wordpress(
        domain=config.wp_domain,
        wp_user=config.wp_user,
        wp_app_password=config.wp_app_password,
        article=article,
        status=config.status,
    )
    featured_image_status = "not_set" if first_attachment_id is None else "pending"
    if first_attachment_id is not None:
        try:
            set_featured_media(
                domain=config.wp_domain,
                wp_user=config.wp_user,
                wp_app_password=config.wp_app_password,
                post_id=int(created.get("id")),
                attachment_id=first_attachment_id,
            )
            featured_image_status = "set"
        except RuntimeError as exc:
            featured_image_status = "failed"
            logger.warning(
                "대표이미지 설정 실패 (post_id=%s, attachment_id=%s): %s",
                created.get("id"), first_attachment_id, exc,
            )
            if not image_message:
                image_message = f"대표이미지 설정 실패: {exc}"
    public_url, pretty_url = choose_public_url(config.wp_domain, created)
    search_submit = {"google": "skipped", "bing": "skipped", "naver": "skipped"}
    if config.submit_search:
        search_submit = submit_post_to_search_sites(public_url, sitemap_url=config.sitemap_url)

    return {
        "post_id": str(created.get("id")),
        "public_url": public_url,
        "pretty_url": pretty_url,
        "edit_url": f"https://{config.wp_domain}/wp-admin/post.php?post={created.get('id')}&action=edit",
        "title": article.title,
        "seo_keyword": article.seo_keyword,
        "image_source": " | ".join(image_sources),
        "image_url": " | ".join(image_urls),
        "image_count_uploaded": str(len(image_urls)),
        "image_status": image_status,
        "image_message": image_message,
        "featured_image_status": featured_image_status,
        "reference_count": str(len(references)),
        "references": " | ".join(x["url"] for x in references),
        "search_submit": str(search_submit),
    }
