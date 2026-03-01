import argparse
import os

from blogbot.clients.openai_client import list_prompt_folders
from blogbot.config import AppConfig
from blogbot.integrations.knowledge_collector import collect_from_site
from blogbot.integrations.knowledge_db import upsert_knowledge_items
from blogbot.workflows.publish import publish_post


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Korean SEO-friendly parenting post with ChatGPT and publish to WordPress."
    )
    parser.add_argument("--topic", default="", help="Topic (required unless --collect-only)")
    parser.add_argument("--main-topic", help="Main topic. Defaults to --topic")
    parser.add_argument("--sub-topics", default="", help="Comma-separated sub topics")
    parser.add_argument(
        "--prompt-folder",
        default="",
        help="Prompt folder name under blogbot/prompt/ (required for publish). Use folder name e.g. '전기차 지원금'",
    )
    parser.add_argument("--image-count", type=int, default=4, help="Number of images to insert (1~5)")
    parser.add_argument("--submit-search", action="store_true", help="Submit sitemap ping to search engines")
    parser.add_argument("--sitemap-url", default="", help="Sitemap URL used for search submission")
    parser.add_argument("--collect-url", default="", help="Collect knowledge data from this site URL and store to DB")
    parser.add_argument("--knowledge-db-path", default="data/knowledge.db", help="SQLite DB path for collected data")
    parser.add_argument("--knowledge-keyword", default="", help="Keyword to load extra references from knowledge DB")
    parser.add_argument("--collect-only", action="store_true", help="Only collect site data to DB and exit")
    parser.add_argument(
        "--status",
        default="draft",
        choices=["draft", "publish", "private"],
        help="WordPress post status",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        help="OpenAI model name",
    )
    parser.add_argument("--openai-api-key", help="OpenAI API key (optional if OPENAI_API_KEY is set)")
    parser.add_argument("--wp-domain", help="WordPress domain (optional if WP_DOMAIN is set)")
    parser.add_argument("--wp-user", help="WordPress user (optional if WP_USER is set)")
    parser.add_argument("--wp-app-password", help="WordPress app password (optional if WP_APP_PASSWORD is set)")
    parser.add_argument("--with-image", action="store_true", help="Download/upload Pixabay image and embed in content")
    parser.add_argument("--pixabay-api-key", help="Pixabay API key (optional if PIXABAY_API_KEY is set)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AppConfig.from_args(args)
    if config.collect_url:
        print(f"Collecting site data: {config.collect_url}")
        collected = collect_from_site(config.collect_url, max_pages=10)
        saved = upsert_knowledge_items(config.knowledge_db_path, collected)
        print(f"Collected items: {len(collected)}")
        if collected:
            preview = " | ".join(x.link for x in collected[:3])
            print(f"Collected links preview: {preview}")
        else:
            print("No pages were collected. The target site may be JS-rendered or blocked for bot requests.")
        print(f"Saved to DB: {config.knowledge_db_path} ({saved} upserted)")
        if config.collect_only:
            return
    if not config.topic.strip():
        raise RuntimeError("--topic is required unless --collect-only is used.")
    if not config.prompt_folder.strip():
        available = list_prompt_folders()
        raise RuntimeError(
            "--prompt-folder is required. Choose a folder under blogbot/prompt/. "
            f"Available: {available if available else '(none found)'}"
        )

    print(f"Topic: {config.topic}")
    print(f"Main topic: {config.main_topic}")
    print(f"Sub topics: {', '.join(config.sub_topics) if config.sub_topics else '(none)'}")
    print(f"Prompt folder: {config.prompt_folder}")
    print(f"Model: {config.model}")
    print("Running publish workflow...")
    result = publish_post(config)

    print("Post created successfully.")
    print(f"Post ID: {result['post_id']}")
    print(f"Link: {result['public_url']}")
    print(f"Pretty Link: {result['pretty_url']}")
    print(f"Edit URL: {result['edit_url']}")
    print(f"Generated title: {result['title']}")
    print(f"SEO keyword: {result['seo_keyword']}")
    print(f"Reference count: {result['reference_count']}")
    if config.knowledge_keyword:
        print(f"Knowledge keyword used: {config.knowledge_keyword}")
    if config.with_image:
        if result["image_url"]:
            print(f"Image uploaded count: {result['image_count_uploaded']}")
            print(f"Image uploaded URLs: {result['image_url']}")
            print(f"Image sources: {result['image_source']}")
        else:
            print(f"Image status: {result['image_status']}")
            if result["image_message"]:
                print(f"Image detail: {result['image_message']}")
    if config.submit_search:
        print(f"Search submit result: {result['search_submit']}")
    if config.status != "publish":
        print("Note: draft/private posts are not public URLs, so opening Link may show 'page not found'.")


if __name__ == "__main__":
    main()
