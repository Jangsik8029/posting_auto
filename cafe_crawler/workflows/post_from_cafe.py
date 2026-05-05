"""크롤링 토픽 후보를 받아 posting_auto의 publish_post() 를 직접 호출."""

from dataclasses import dataclass
from types import SimpleNamespace

from blogbot.config import AppConfig
from blogbot.models import PublishResult
from blogbot.workflows.publish import publish_post

from .topic_selector import TopicCandidate


@dataclass
class PostFromCafeResult:
    config_summary: dict
    publish_result: PublishResult | None
    dry_run: bool


def _build_config(
    candidate: TopicCandidate,
    prompt_folder: str,
    status: str,
    with_image: bool,
    image_source: str,
    knowledge_keyword: str | None,
    model: str,
) -> AppConfig:
    """AppConfig.from_args 가 argparse Namespace 처럼 getattr 로 읽으므로 SimpleNamespace 사용."""
    ns = SimpleNamespace(
        topic=candidate.main_topic,
        main_topic=candidate.main_topic,
        sub_topics=",".join(candidate.sub_topics),
        prompt_folder=prompt_folder,
        image_count=4,
        submit_search=False,
        sitemap_url="",
        knowledge_db_path="data/knowledge.db",
        knowledge_keyword=knowledge_keyword or candidate.source_keyword,
        collect_url="",
        collect_only=False,
        status=status,
        with_image=with_image,
        image_source=image_source,
        model=model,
        openai_api_key=None,
        wp_domain=None,
        wp_user=None,
        wp_app_password=None,
        pixabay_api_key=None,
    )
    return AppConfig.from_args(ns)


def post_from_cafe(
    candidate: TopicCandidate,
    prompt_folder: str,
    status: str = "draft",
    with_image: bool = False,
    image_source: str = "pixabay",
    knowledge_keyword: str | None = None,
    model: str = "gpt-4o-mini",
    dry_run: bool = False,
) -> PostFromCafeResult:
    config = _build_config(
        candidate=candidate,
        prompt_folder=prompt_folder,
        status=status,
        with_image=with_image,
        image_source=image_source,
        knowledge_keyword=knowledge_keyword,
        model=model,
    )

    summary = {
        "topic": config.topic,
        "main_topic": config.main_topic,
        "sub_topics": config.sub_topics,
        "prompt_folder": config.prompt_folder,
        "knowledge_keyword": config.knowledge_keyword,
        "status": config.status,
        "with_image": config.with_image,
        "image_source": config.image_source,
        "model": config.model,
    }

    if dry_run:
        return PostFromCafeResult(config_summary=summary, publish_result=None, dry_run=True)

    config.validate("publish")
    result = publish_post(config)
    return PostFromCafeResult(config_summary=summary, publish_result=result, dry_run=False)
