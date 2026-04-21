from dataclasses import dataclass
import os

from blogbot.utils import normalize_domain


# 시크릿은 환경 변수(.env) 또는 UI 입력으로만 주입한다.
# 소스 코드에 API 키·비밀번호를 하드코딩하지 말 것.


def read_required_env(name: str, aliases: tuple[str, ...] = ()) -> str:
    names = (name, *aliases)
    for key in names:
        value = os.getenv(key, "").strip()
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def pick_config(cli_value: str | None, env_name: str, env_aliases: tuple[str, ...] = ()) -> str:
    if cli_value and cli_value.strip():
        return cli_value.strip()
    return read_required_env(env_name, env_aliases)


class ConfigValidationError(RuntimeError):
    """AppConfig.validate 가 필수 필드 누락을 발견했을 때 발생."""


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
    image_source: str  # "local" | "title" | "dalle" | "pixabay"
    knowledge_db_path: str
    knowledge_keyword: str
    collect_url: str
    collect_only: bool

    @classmethod
    def from_args(cls, args: object) -> "AppConfig":
        collect_only = bool(getattr(args, "collect_only", False))
        with_image = bool(getattr(args, "with_image"))

        image_source = (getattr(args, "image_source", "local") or "local").strip().lower()
        if image_source not in ("local", "title", "dalle", "pixabay"):
            image_source = "local"

        pixabay_api_key = ""
        if with_image and not collect_only and image_source == "pixabay":
            pixabay_api_key = pick_config(
                getattr(args, "pixabay_api_key"),
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
                getattr(args, "openai_api_key"), "OPENAI_API_KEY", ("OPENAI_API",)
            )
            wp_domain = normalize_domain(pick_config(getattr(args, "wp_domain"), "WP_DOMAIN"))
            wp_user = pick_config(getattr(args, "wp_user"), "WP_USER")
            wp_app_password = pick_config(getattr(args, "wp_app_password"), "WP_APP_PASSWORD")

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
            image_source=image_source,
            knowledge_db_path=knowledge_db_path,
            knowledge_keyword=knowledge_keyword,
            collect_url=collect_url,
            collect_only=collect_only,
        )

    def validate(self, for_operation: str) -> None:
        missing: list[str] = []
        if for_operation == "publish":
            if not self.topic.strip():
                missing.append("topic")
            if not self.prompt_folder.strip():
                missing.append("prompt_folder")
            if not self.openai_api_key.strip():
                missing.append("openai_api_key")
            if not self.wp_domain.strip():
                missing.append("wp_domain")
            if not self.wp_user.strip():
                missing.append("wp_user")
            if not self.wp_app_password.strip():
                missing.append("wp_app_password")
            if self.with_image and self.image_source == "pixabay" and not self.pixabay_api_key.strip():
                missing.append("pixabay_api_key")
        elif for_operation == "reoptimize":
            if not self.wp_domain.strip():
                missing.append("wp_domain")
            if not self.wp_user.strip():
                missing.append("wp_user")
            if not self.wp_app_password.strip():
                missing.append("wp_app_password")
        elif for_operation == "collect":
            if not self.collect_url.strip():
                missing.append("collect_url")
        else:
            raise ValueError(f"Unknown operation for validate(): {for_operation}")

        if missing:
            raise ConfigValidationError(
                f"{for_operation} 작업에 필요한 값이 없습니다: {', '.join(missing)}"
            )
