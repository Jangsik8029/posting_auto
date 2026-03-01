from dataclasses import dataclass


@dataclass
class Article:
    title: str
    excerpt: str
    content_html: str
    seo_keyword: str

