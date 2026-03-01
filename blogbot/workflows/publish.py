from blogbot.clients.openai_client import generate_article_with_chatgpt
from blogbot.clients.pixabay_client import download_images_with_pixabay, save_image_locally
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
    if not image_urls:
        return content_html

    if "<h2" not in content_html:
        blocks = [f'<p><img src="{u}" alt="{title}" /></p>' for u in image_urls]
        return "\n".join(blocks) + "\n" + content_html

    parts = content_html.split("<h2")
    rebuilt = parts[0]
    image_idx = 0

    if image_idx < len(image_urls):
        rebuilt = f'<p><img src="{image_urls[image_idx]}" alt="{title}" /></p>\n' + rebuilt
        image_idx += 1

    for p in parts[1:]:
        if image_idx < len(image_urls):
            rebuilt += f'\n<p><img src="{image_urls[image_idx]}" alt="{title}" /></p>\n'
            image_idx += 1
        rebuilt += "<h2" + p

    while image_idx < len(image_urls):
        rebuilt += f'\n<p><img src="{image_urls[image_idx]}" alt="{title}" /></p>\n'
        image_idx += 1
    return rebuilt


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
    first_attachment_id: int | None = None
    image_status = "not_requested"
    image_message = ""

    if config.with_image:
        image_status = "requested"
        query = " ".join([config.main_topic, *config.sub_topics]).strip()
        downloaded = download_images_with_pixabay(query, config.pixabay_api_key, count=config.image_count)

        for i, (image_bytes, source_url) in enumerate(downloaded, start=1):
            image_path = save_image_locally(image_bytes, query or config.topic, ext="jpg", index=i)
            try:
                media = upload_media_xmlrpc(
                    domain=config.wp_domain,
                    wp_user=config.wp_user,
                    wp_app_password=config.wp_app_password,
                    file_path=image_path,
                )
                image_url = str(media.get("url", "")).strip()
                if image_url:
                    image_urls.append(image_url)
                    image_sources.append(source_url)
                if first_attachment_id is None:
                    aid = media.get("id")
                    if aid is not None:
                        first_attachment_id = int(aid) if isinstance(aid, str) else int(aid)
            except RuntimeError as exc:
                if "413" not in str(exc):
                    raise
                image_message = str(exc)

        if image_urls:
            article.content_html = _inject_images_into_content(article.content_html, article.title, image_urls)
            image_status = "uploaded"
        else:
            image_status = "upload_skipped"

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
