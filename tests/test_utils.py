"""utils 헬퍼 스모크."""
from __future__ import annotations

import pytest

from blogbot.utils import (
    extract_json_object,
    normalize_domain,
    slugify_korean_friendly,
    strip_html,
    truncate_with_ellipsis,
    xml_escape,
)


def test_truncate_short_returns_as_is() -> None:
    assert truncate_with_ellipsis("짧은 텍스트", 100) == "짧은 텍스트"


def test_truncate_long_adds_ellipsis() -> None:
    text = "a" * 50
    out = truncate_with_ellipsis(text, 10)
    assert len(out) == 10
    assert out.endswith("…")


def test_truncate_zero_or_negative() -> None:
    assert truncate_with_ellipsis("whatever", 0) == ""


def test_truncate_smaller_than_ellipsis() -> None:
    out = truncate_with_ellipsis("abcdef", 1)
    assert out == "a"


def test_slugify_keeps_hangul_and_ascii() -> None:
    slug = slugify_korean_friendly("강릉  맛집 Top 5!")
    assert "강릉" in slug
    assert "맛집" in slug
    assert "-" in slug
    assert "!" not in slug


def test_slugify_empty_fallback() -> None:
    assert slugify_korean_friendly("   ") == "auto-post"


def test_extract_json_object_plain() -> None:
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_with_prose() -> None:
    raw = 'Here is the answer:\n```json\n{"title": "t", "body": "b"}\n```'
    assert extract_json_object(raw) == {"title": "t", "body": "b"}


def test_extract_json_object_invalid_raises() -> None:
    with pytest.raises(ValueError):
        extract_json_object("not a json at all")


def test_xml_escape_all_special_chars() -> None:
    escaped = xml_escape("<a href=\"x\">A&B's</a>")
    assert "&lt;" in escaped
    assert "&gt;" in escaped
    assert "&amp;" in escaped
    assert "&quot;" in escaped
    assert "&apos;" in escaped


def test_normalize_domain_strips_scheme_and_slash() -> None:
    assert normalize_domain("https://Example.com/") == "Example.com"
    assert normalize_domain("  http://foo.bar/baz/  ") == "foo.bar/baz"


def test_strip_html_unescapes_entities() -> None:
    assert strip_html("<p>Tom &amp; Jerry</p>") == "Tom & Jerry"
