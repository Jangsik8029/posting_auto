"""기존 글을 네이버 검색엔진 최적화(SEO) 가이드에 맞게 보정한다."""
import re

from blogbot.clients.wordpress_client import get_post_from_wordpress, update_post_on_wordpress
from blogbot.models import Article


def reoptimize_post_naver_seo(
    domain: str,
    wp_user: str,
    wp_app_password: str,
    post_id: int,
    title_max: int = 55,
    excerpt_max: int = 155,
) -> dict[str, str]:
    """
    워드프레스 글 한 건을 가져와 네이버 SEO 보정 후 다시 저장한다.
    반환: post_id, title, excerpt_preview, status 등.
    """
    article = get_post_from_wordpress(domain, wp_user, wp_app_password, post_id)
    rewritten = rewrite_article_for_naver_seo(article, title_max=title_max, excerpt_max=excerpt_max)
    result = update_post_on_wordpress(domain, wp_user, wp_app_password, post_id, rewritten)
    return {
        "post_id": str(post_id),
        "title": rewritten.title,
        "excerpt_preview": (rewritten.excerpt[:60] + "…") if len(rewritten.excerpt) > 60 else rewritten.excerpt,
        "status": "updated",
    }


def rewrite_article_for_naver_seo(article: Article, title_max: int = 55, excerpt_max: int = 155) -> Article:
    """
    제목·요약 길이, 본문 H1 개수, 이미지 alt를 네이버 가이드에 맞게 보정한다.
    - title: 25~55자 권장 → 초과 시 잘라 말줄임
    - excerpt: 120~155자 권장 → 초과 시 잘라 말줄임
    - 본문: H1 → H2 치환 (H1 1개만 되도록)
    - img: alt 없는 경우 제목 기반 alt 추가
    """
    title = article.title.strip()
    excerpt = article.excerpt.strip()
    content = article.content_html

    if len(title) > title_max:
        title = (title[: title_max - 1] + "…") if title_max > 1 else title[:title_max]
    if len(excerpt) > excerpt_max:
        excerpt = (excerpt[: excerpt_max - 1] + "…") if excerpt_max > 1 else excerpt[:excerpt_max]

    content = content.replace("<h1 ", "<h2 ").replace("</h1>", "</h2>")

    def _ensure_alt(match: re.Match) -> str:
        full = match.group(0)
        if "alt=" in full:
            return full
        before_slash = full.rstrip("/ ")
        if before_slash.endswith(">"):
            insert = f' alt="{title} 관련 이미지"'
            return before_slash[:-1] + insert + ">"
        return full

    content = re.sub(r"<img\s+[^>]*>", _ensure_alt, content, flags=re.IGNORECASE)

    return Article(
        title=title,
        excerpt=excerpt,
        content_html=content,
        seo_keyword=article.seo_keyword or title,
    )
