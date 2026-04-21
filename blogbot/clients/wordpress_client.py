import base64
import logging
import mimetypes
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests

from blogbot.clients.http import TIMEOUT_DEFAULT, TIMEOUT_LONG, TIMEOUT_SHORT, get_shared_session
from blogbot.models import Article
from blogbot.utils import (
    normalize_domain,
    sanitize_app_password,
    slugify_korean_friendly,
    strip_html,
    truncate_with_ellipsis,
    xml_escape,
)

logger = logging.getLogger(__name__)

# XML-RPC 호출에서 기본 블로그 ID (단일 사이트 환경 기준).
XMLRPC_BLOG_ID = 1
_XML_RPC_HEADERS = {"Content-Type": "text/xml"}


def looks_like_json_api_response(response: requests.Response) -> bool:
    content_type = response.headers.get("Content-Type", "").lower()
    final_url = response.url.lower()
    if "application/json" not in content_type:
        return False
    if "errdoc.gabia.io" in final_url:
        return False
    return True


def build_wp_api_endpoint(domain: str, route: str) -> str:
    normalized_domain = normalize_domain(domain)
    normalized_route = route.strip("/")
    pretty_url = f"https://{normalized_domain}/wp-json/{normalized_route}"
    query_url = f"https://{normalized_domain}/?rest_route=/{normalized_route}"

    try:
        probe = get_shared_session().get(pretty_url, timeout=TIMEOUT_SHORT, allow_redirects=True)
        if looks_like_json_api_response(probe):
            return pretty_url
    except requests.RequestException as exc:
        logger.warning(
            "WP pretty endpoint probe failed (%s); falling back to query URL: %s",
            pretty_url, exc,
        )

    return query_url


def _xmlrpc_param_value(value: Any) -> str:
    """XML-RPC <param><value>...</value></param> 요소 한 개를 생성한다."""
    if isinstance(value, bool):
        return f"<param><value><boolean>{1 if value else 0}</boolean></value></param>"
    if isinstance(value, int):
        return f"<param><value><int>{value}</int></value></param>"
    if isinstance(value, str):
        return f"<param><value><string>{xml_escape(value)}</string></value></param>"
    if isinstance(value, dict):
        members = "".join(
            f"<member><name>{xml_escape(str(k))}</name>{_xmlrpc_inline_value(v)}</member>"
            for k, v in value.items()
        )
        return f"<param><value><struct>{members}</struct></value></param>"
    raise TypeError(f"Unsupported XML-RPC value type: {type(value).__name__}")


def _xmlrpc_inline_value(value: Any) -> str:
    """struct 멤버 내부 <value> 요소 한 개."""
    if isinstance(value, bool):
        return f"<value><boolean>{1 if value else 0}</boolean></value>"
    if isinstance(value, int):
        return f"<value><int>{value}</int></value>"
    if isinstance(value, str):
        return f"<value><string>{xml_escape(value)}</string></value>"
    if isinstance(value, dict):
        members = "".join(
            f"<member><name>{xml_escape(str(k))}</name>{_xmlrpc_inline_value(v)}</member>"
            for k, v in value.items()
        )
        return f"<value><struct>{members}</struct></value>"
    # 특수: 이미 만들어진 XML 조각은 별도 래퍼로 전달하도록 Raw 클래스 쓰는게 깔끔하지만
    # 현재는 사용처가 없어 base64 만 별도 처리한다.
    raise TypeError(f"Unsupported XML-RPC inline value type: {type(value).__name__}")


def _build_xmlrpc_call(method_name: str, params: list[Any]) -> str:
    param_xml = "".join(_xmlrpc_param_value(p) for p in params)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<methodCall><methodName>{xml_escape(method_name)}</methodName>"
        f"<params>{param_xml}</params></methodCall>"
    )


def _build_upload_media_body(wp_user: str, wp_password: str, file_path: Path, bits_b64: str) -> str:
    """wp.uploadFile 은 bits 값이 base64 바이너리라서 별도 빌더가 필요하다."""
    mime_type = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<methodCall><methodName>wp.uploadFile</methodName><params>"
        f"<param><value><int>{XMLRPC_BLOG_ID}</int></value></param>"
        f"<param><value><string>{xml_escape(wp_user)}</string></value></param>"
        f"<param><value><string>{xml_escape(wp_password)}</string></value></param>"
        "<param><value><struct>"
        f"<member><name>name</name><value><string>{xml_escape(file_path.name)}</string></value></member>"
        f"<member><name>type</name><value><string>{xml_escape(mime_type)}</string></value></member>"
        f"<member><name>bits</name><value><base64>{bits_b64}</base64></value></member>"
        "<member><name>overwrite</name><value><boolean>1</boolean></value></member>"
        "</struct></value></param>"
        "</params></methodCall>"
    )


def _post_xmlrpc(url: str, body: str, timeout: int) -> requests.Response:
    return get_shared_session().post(
        url, data=body.encode("utf-8"), headers=_XML_RPC_HEADERS, timeout=timeout
    )


def _raise_if_xmlrpc_failed(response: requests.Response, context: str) -> ET.Element:
    """응답을 파싱하고 HTTP/fault 를 확인 후 root element 반환."""
    if response.status_code != 200:
        logger.debug("WP %s response body: %s", context, response.text)
        raise RuntimeError(
            f"WordPress {context} failed ({response.status_code}): "
            f"{truncate_with_ellipsis(response.text, 300)}"
        )
    root = ET.fromstring(response.text)
    fault = root.find(".//fault")
    if fault is not None:
        message = " ".join("".join(fault.itertext()).split())
        raise RuntimeError(f"WordPress {context} fault: {message}")
    return root


def upload_media_xmlrpc(domain: str, wp_user: str, wp_app_password: str, file_path: Path) -> dict[str, Any]:
    normalized_domain = normalize_domain(domain)
    xmlrpc_url = f"https://{normalized_domain}/xmlrpc.php"
    bits_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
    xml_body = _build_upload_media_body(
        wp_user=wp_user,
        wp_password=sanitize_app_password(wp_app_password),
        file_path=file_path,
        bits_b64=bits_b64,
    )
    response = _post_xmlrpc(xmlrpc_url, xml_body, TIMEOUT_LONG // 2)  # 60s
    root = _raise_if_xmlrpc_failed(response, "media upload")

    result: dict[str, Any] = {}
    for member in root.findall(".//params/param/value/struct/member"):
        key = member.findtext("name")
        value_node = member.find("value")
        value = "".join(value_node.itertext()).strip() if value_node is not None else ""
        if key:
            result[key] = value
    return result


def set_featured_media(
    domain: str,
    wp_user: str,
    wp_app_password: str,
    post_id: int,
    attachment_id: int,
) -> None:
    """Set the post's featured image (대표이미지). Tries REST API first, then XML-RPC."""
    normalized_domain = normalize_domain(domain)
    auth = (wp_user, sanitize_app_password(wp_app_password))
    headers = {
        "User-Agent": "python-requests/wordpress-autowriter",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    url = build_wp_api_endpoint(domain, f"wp/v2/posts/{post_id}")
    try:
        resp = get_shared_session().patch(
            url,
            auth=auth,
            headers=headers,
            json={"featured_media": attachment_id},
            timeout=TIMEOUT_DEFAULT,
        )
        if resp.status_code in (200, 204):
            return
        logger.info(
            "REST featured media set returned %s, falling back to XML-RPC (post_id=%s)",
            resp.status_code, post_id,
        )
    except requests.RequestException as exc:
        logger.warning(
            "REST featured media set failed for post_id=%s, falling back to XML-RPC: %s",
            post_id, exc,
        )

    xmlrpc_url = f"https://{normalized_domain}/xmlrpc.php"
    xml_body = _build_xmlrpc_call(
        "wp.editPost",
        [
            XMLRPC_BLOG_ID,
            wp_user,
            sanitize_app_password(wp_app_password),
            int(post_id),
            {"post_thumbnail": int(attachment_id)},
        ],
    )
    response = _post_xmlrpc(xmlrpc_url, xml_body, TIMEOUT_DEFAULT)
    _raise_if_xmlrpc_failed(response, "set featured image")


def post_to_wordpress_xmlrpc(
    domain: str, wp_user: str, wp_app_password: str, article: Article, status: str
) -> dict[str, Any]:
    normalized_domain = normalize_domain(domain)
    xmlrpc_url = f"https://{normalized_domain}/xmlrpc.php"
    post_status = "publish" if status == "publish" else "draft"
    xml_body = _build_xmlrpc_call(
        "wp.newPost",
        [
            XMLRPC_BLOG_ID,
            wp_user,
            sanitize_app_password(wp_app_password),
            {
                "post_type": "post",
                "post_status": post_status,
                "post_title": article.title,
                "post_content": article.content_html,
                "mt_excerpt": article.excerpt,
            },
        ],
    )
    response = _post_xmlrpc(xmlrpc_url, xml_body, TIMEOUT_DEFAULT)
    root = _raise_if_xmlrpc_failed(response, "XML-RPC post")

    post_id_text = root.findtext(".//params/param/value/string") or root.findtext(".//params/param/value/int")
    if not post_id_text:
        raise RuntimeError("WordPress XML-RPC succeeded but post_id was not returned.")

    post_id = int(post_id_text)
    return {"id": post_id, "link": f"https://{normalized_domain}/?p={post_id}"}


def post_to_wordpress(
    domain: str,
    wp_user: str,
    wp_app_password: str,
    article: Article,
    status: str,
) -> dict[str, Any]:
    url = build_wp_api_endpoint(domain, "wp/v2/posts")
    auth = (wp_user, sanitize_app_password(wp_app_password))
    headers = {
        "User-Agent": "python-requests/wordpress-autowriter",
        "Accept": "application/json",
    }
    payload = {
        "title": article.title,
        "content": article.content_html,
        "excerpt": article.excerpt,
        "status": status,
        "slug": slugify_korean_friendly(article.title),
    }

    session = get_shared_session()
    me_url = build_wp_api_endpoint(domain, "wp/v2/users/me")
    me_resp = session.get(me_url, auth=auth, headers=headers, timeout=TIMEOUT_DEFAULT)
    if me_resp.status_code != 200:
        try:
            me_json = me_resp.json()
            err_code = me_json.get("code", "")
            err_message = me_json.get("message", "")
        except ValueError:
            err_code = ""
            err_message = truncate_with_ellipsis(me_resp.text, 200)
        if err_code == "rest_not_logged_in":
            return post_to_wordpress_xmlrpc(domain, wp_user, wp_app_password, article, status)
        raise RuntimeError(
            f"WordPress auth preflight failed ({me_resp.status_code}) [{err_code}] {err_message}. endpoint={me_url}"
        )

    response = session.post(url, auth=auth, headers=headers, data=payload, timeout=TIMEOUT_DEFAULT)
    if response.status_code != 201:
        if response.status_code in {401, 403}:
            try:
                err_json = response.json()
                err_code = err_json.get("code", "")
                err_message = err_json.get("message", "")
            except ValueError:
                err_code = ""
                err_message = truncate_with_ellipsis(response.text, 200)
            raise RuntimeError(
                f"WordPress auth/permission failed ({response.status_code}) [{err_code}] {err_message}. endpoint={url}"
            )
        logger.debug("WP post full response body: %s", response.text)
        raise RuntimeError(
            f"WordPress post failed ({response.status_code}) on {url}: "
            f"{truncate_with_ellipsis(response.text, 300)}"
        )
    return response.json()


def get_post_from_wordpress(
    domain: str,
    wp_user: str,
    wp_app_password: str,
    post_id: int,
) -> Article:
    """워드프레스에서 글 한 건을 가져와 Article로 반환한다."""
    url = build_wp_api_endpoint(domain, f"wp/v2/posts/{post_id}")
    auth = (wp_user, sanitize_app_password(wp_app_password))
    headers = {
        "User-Agent": "python-requests/wordpress-autowriter",
        "Accept": "application/json",
    }
    resp = get_shared_session().get(url, auth=auth, headers=headers, timeout=TIMEOUT_DEFAULT)
    if resp.status_code != 200:
        logger.debug("WP get post body: %s", resp.text)
        raise RuntimeError(
            f"WordPress get post failed ({resp.status_code}): "
            f"{truncate_with_ellipsis(resp.text, 300)}"
        )
    data = resp.json()
    title = (data.get("title") or {}).get("rendered", "") or ""
    if isinstance(title, str):
        title = strip_html(title)
    content = (data.get("content") or {}).get("rendered", "") or ""
    excerpt = (data.get("excerpt") or {}).get("rendered", "") or ""
    if isinstance(excerpt, str):
        excerpt = strip_html(excerpt)
    return Article(
        title=title,
        excerpt=excerpt,
        content_html=content,
        seo_keyword=title,
    )


def update_post_on_wordpress(
    domain: str,
    wp_user: str,
    wp_app_password: str,
    post_id: int,
    article: Article,
) -> dict[str, Any]:
    """워드프레스 글을 수정한다 (title, content, excerpt)."""
    url = build_wp_api_endpoint(domain, f"wp/v2/posts/{post_id}")
    auth = (wp_user, sanitize_app_password(wp_app_password))
    headers = {
        "User-Agent": "python-requests/wordpress-autowriter",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "title": article.title,
        "content": article.content_html,
        "excerpt": article.excerpt,
    }
    resp = get_shared_session().patch(url, auth=auth, headers=headers, json=payload, timeout=TIMEOUT_DEFAULT)
    if resp.status_code not in (200, 204):
        logger.debug("WP update post body: %s", resp.text)
        raise RuntimeError(
            f"WordPress update post failed ({resp.status_code}): "
            f"{truncate_with_ellipsis(resp.text, 300)}"
        )
    return resp.json() if resp.text else {"id": post_id}


def choose_public_url(domain: str, created: dict[str, Any]) -> tuple[str, str]:
    normalized_domain = normalize_domain(domain)
    post_id = created.get("id")
    pretty_link = str(created.get("link") or "").strip()
    fallback_link = f"https://{normalized_domain}/?p={post_id}"

    if not pretty_link:
        return fallback_link, fallback_link
    try:
        check = get_shared_session().get(pretty_link, timeout=TIMEOUT_SHORT, allow_redirects=True)
        if check.status_code >= 400:
            logger.info("Pretty link %s returned %s; using fallback link.", pretty_link, check.status_code)
            return fallback_link, pretty_link
    except requests.RequestException as exc:
        logger.warning("Pretty link check failed for %s: %s", pretty_link, exc)
        return fallback_link, pretty_link
    return fallback_link, pretty_link
