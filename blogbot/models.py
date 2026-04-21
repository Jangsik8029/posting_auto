from dataclasses import dataclass
from typing import TypedDict


@dataclass
class Article:
    title: str
    excerpt: str
    content_html: str
    seo_keyword: str


class PublishResult(TypedDict):
    post_id: str
    public_url: str
    pretty_url: str
    edit_url: str
    title: str
    seo_keyword: str
    image_source: str
    image_url: str
    image_count_uploaded: str
    image_status: str
    image_message: str
    featured_image_status: str
    reference_count: str
    references: str
    search_submit: str


class ReoptimizeResult(TypedDict):
    post_id: str
    title: str
    excerpt_preview: str
    status: str
