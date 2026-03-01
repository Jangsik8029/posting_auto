from dataclasses import dataclass
import os

from blogbot.utils import normalize_domain


# Keep empty by default. Fill these only if you intentionally want inline secrets.
INLINE_OPENAI_API_KEY = ""
INLINE_WP_DOMAIN = "logofknowledge.com"
INLINE_WP_USER = "jangsik0044"
INLINE_WP_APP_PASSWORD = "nUXG R2n5 voIE YZjl 53la R0Pm"
INLINE_PIXABAY_API_KEY = "54648007-5c379f160bd1556920395fe89"


def read_required_env(name: str, aliases: tuple[str, ...] = ()) -> str:
    names = (name, *aliases)
    for key in names:
        value = os.getenv(key, "").strip()
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def pick_config(
    cli_value: str | None, inline_value: str, env_name: str, env_aliases: tuple[str, ...] = ()
) -> str:
    if cli_value and cli_value.strip():
        return cli_value.strip()
    if inline_value.strip():
        return inline_value.strip()
    return read_required_env(env_name, env_aliases)


@dataclass
class AppConfig:
    openai_api_key: str
    wp_domain: str
    wp_user: str
    wp_app_password: str
    pixabay_api_key: str
    model: str
    topic: str
    main_topic: str
    sub_topics: list[str]
    prompt_folder: str
    image_count: int
    submit_search: bool
    sitemap_url: str
    status: str
    with_image: bool
    knowledge_db_path: str
    knowledge_keyword: str
    collect_url: str
    collect_only: bool

    @classmethod
    def from_args(cls, args: object) -> "AppConfig":
        collect_only = bool(getattr(args, "collect_only", False))
        with_image = bool(getattr(args, "with_image"))
        pixabay_api_key = ""
        if with_image and not collect_only:
            pixabay_api_key = pick_config(
                getattr(args, "pixabay_api_key"),
                INLINE_PIXABAY_API_KEY,
                "PIXABAY_API_KEY",
            )

        topic = getattr(args, "topic")
        main_topic = (getattr(args, "main_topic", "") or topic).strip()
        sub_topics_raw = (getattr(args, "sub_topics", "") or "").strip()
        sub_topics = [x.strip() for x in sub_topics_raw.split(",") if x.strip()]
        prompt_folder = (getattr(args, "prompt_folder", "") or "").strip()
        image_count = int(getattr(args, "image_count", 4) or 4)
        if image_count < 1:
            image_count = 1
        if image_count > 5:
            image_count = 5

        submit_search = bool(getattr(args, "submit_search", False))
        sitemap_url = (getattr(args, "sitemap_url", "") or "").strip()
        knowledge_db_path = (getattr(args, "knowledge_db_path", "data/knowledge.db") or "data/knowledge.db").strip()
        knowledge_keyword = (getattr(args, "knowledge_keyword", "") or "").strip()
        collect_url = (getattr(args, "collect_url", "") or "").strip()

        openai_api_key = ""
        wp_domain = ""
        wp_user = ""
        wp_app_password = ""
        if not collect_only:
            openai_api_key = pick_config(
                getattr(args, "openai_api_key"), INLINE_OPENAI_API_KEY, "OPENAI_API_KEY", ("OPENAI_API",)
            )
            wp_domain = normalize_domain(pick_config(getattr(args, "wp_domain"), INLINE_WP_DOMAIN, "WP_DOMAIN"))
            wp_user = pick_config(getattr(args, "wp_user"), INLINE_WP_USER, "WP_USER")
            wp_app_password = pick_config(
                getattr(args, "wp_app_password"), INLINE_WP_APP_PASSWORD, "WP_APP_PASSWORD"
            )

        return cls(
            openai_api_key=openai_api_key,
            wp_domain=wp_domain,
            wp_user=wp_user,
            wp_app_password=wp_app_password,
            pixabay_api_key=pixabay_api_key,
            model=getattr(args, "model"),
            topic=topic,
            main_topic=main_topic,
            sub_topics=sub_topics,
            prompt_folder=prompt_folder,
            image_count=image_count,
            submit_search=submit_search,
            sitemap_url=sitemap_url,
            status=getattr(args, "status"),
            with_image=with_image,
            knowledge_db_path=knowledge_db_path,
            knowledge_keyword=knowledge_keyword,
            collect_url=collect_url,
            collect_only=collect_only,
        )
