"""rewrite_article_for_naver_seo 규칙 스모크."""
from __future__ import annotations

from blogbot.models import Article
from blogbot.workflows.rewrite_seo import rewrite_article_for_naver_seo


def _article(title: str = "T", excerpt: str = "E", content: str = "<p>x</p>") -> Article:
    return Article(title=title, excerpt=excerpt, content_html=content, seo_keyword="")


def test_title_truncated_to_max() -> None:
    long_title = "가" * 100
    out = rewrite_article_for_naver_seo(_article(title=long_title), title_max=55)
    assert len(out.title) == 55
    assert out.title.endswith("…")


def test_excerpt_truncated_to_max() -> None:
    long_excerpt = "나" * 300
    out = rewrite_article_for_naver_seo(_article(excerpt=long_excerpt), excerpt_max=155)
    assert len(out.excerpt) == 155


def test_h1_replaced_with_h2() -> None:
    html = '<h1 class="x">제목</h1><p>본문</p>'
    out = rewrite_article_for_naver_seo(_article(content=html))
    assert "<h1" not in out.content_html
    assert "<h2" in out.content_html
    assert "</h2>" in out.content_html


def test_img_without_alt_gets_alt_added() -> None:
    html = '<p><img src="a.jpg" /></p>'
    out = rewrite_article_for_naver_seo(_article(title="강릉", content=html))
    assert "alt=" in out.content_html
    assert "강릉" in out.content_html


def test_img_with_alt_is_preserved() -> None:
    html = '<p><img src="a.jpg" alt="기존 alt" /></p>'
    out = rewrite_article_for_naver_seo(_article(content=html))
    assert out.content_html.count("alt=") == 1
    assert "기존 alt" in out.content_html


def test_seo_keyword_falls_back_to_title_when_missing() -> None:
    out = rewrite_article_for_naver_seo(_article(title="타이틀"))
    assert out.seo_keyword == "타이틀"
