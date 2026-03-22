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
from blogbot.models import Article


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


def _upload_single_image(
    config: AppConfig,
    image_path: Path,
    source_label: str,
    image_urls: list[str],
    image_sources: list[str],
    attachment_ids: list[int],
) -> str:
    """이미지 한 장을 WP에 업로드하고 결과를 리스트에 추가한다. 에러 메시지를 반환."""
    try:
        media = upload_media_xmlrpc(
            domain=config.wp_domain,
            wp_user=config.wp_user,
            wp_app_password=config.wp_app_password,
            file_path=image_path,
        )
        wp_url = str(media.get("url", "")).strip()
        if wp_url:
            image_urls.append(wp_url)
            image_sources.append(source_label)
        if not attachment_ids:
            aid = media.get("id")
            if aid is not None:
                attachment_ids.append(int(aid))
    except RuntimeError as exc:
        if "413" not in str(exc):
            raise
        return str(exc)
    return ""


def publish_post(config: AppConfig) -> dict[str, str]:
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

        if config.image_source == "local":
            prompt_dir = PROMPT_ROOT / config.prompt_folder.strip()
            local_paths = load_local_images(prompt_dir, count=config.image_count)
            if not local_paths:
                image_status = "upload_skipped"
                image_message = "프롬프트 폴더에 이미지 파일이 없습니다."
            else:
                for image_path in local_paths:
                    msg = _upload_single_image(config, image_path, f"local:{image_path.name}",
                                               image_urls, image_sources, attachment_ids)
                    if msg:
                        image_message = msg

        elif config.image_source == "title":
            title_label = query or config.topic
            for i in range(1, config.image_count + 1):
                image_path = save_title_thumbnail(title_label, index=i)
                msg = _upload_single_image(config, image_path, f"title-gen:{image_path.name}",
                                           image_urls, image_sources, attachment_ids)
                if msg:
                    image_message = msg

        else:
            if config.image_source == "dalle":
                downloaded = generate_images_with_dalle(
                    topic=query or config.topic,
                    api_key=config.openai_api_key,
                    count=config.image_count,
                )
            else:
                downloaded = download_images_with_pixabay(query, config.pixabay_api_key, count=config.image_count)

            for i, (image_bytes, source_url) in enumerate(downloaded, start=1):
                if config.image_source == "dalle":
                    image_path = save_dalle_image_locally(image_bytes, query or config.topic, index=i)
                else:
                    image_path = save_image_locally(image_bytes, query or config.topic, ext="jpg", index=i)
                msg = _upload_single_image(config, image_path, source_url,
                                           image_urls, image_sources, attachment_ids)
                if msg:
                    image_message = msg

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
    if first_attachment_id is not None:
        try:
            set_featured_media(
                domain=config.wp_domain,
                wp_user=config.wp_user,
                wp_app_password=config.wp_app_password,
                post_id=int(created.get("id")),
                attachment_id=first_attachment_id,
            )
        except RuntimeError:
            pass
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
        "reference_count": str(len(references)),
        "references": " | ".join(x["url"] for x in references),
        "search_submit": str(search_submit),
    }
