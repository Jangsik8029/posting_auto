import base64
import mimetypes
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests

from blogbot.models import Article
from blogbot.utils import normalize_domain, sanitize_app_password, slugify_korean_friendly, xml_escape


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
        probe = requests.get(pretty_url, timeout=10, allow_redirects=True)
        if looks_like_json_api_response(probe):
            return pretty_url
    except requests.RequestException:
        pass

    return query_url


def _build_xmlrpc_new_post_body(wp_user: str, wp_password: str, article: Article, status: str) -> str:
    post_status = "publish" if status == "publish" else "draft"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<methodCall>
  <methodName>wp.newPost</methodName>
  <params>
    <param><value><int>1</int></value></param>
    <param><value><string>{xml_escape(wp_user)}</string></value></param>
    <param><value><string>{xml_escape(wp_password)}</string></value></param>
    <param><value><struct>
      <member><name>post_type</name><value><string>post</string></value></member>
      <member><name>post_status</name><value><string>{post_status}</string></value></member>
      <member><name>post_title</name><value><string>{xml_escape(article.title)}</string></value></member>
      <member><name>post_content</name><value><string>{xml_escape(article.content_html)}</string></value></member>
      <member><name>mt_excerpt</name><value><string>{xml_escape(article.excerpt)}</string></value></member>
    </struct></value></param>
  </params>
</methodCall>"""


def _build_xmlrpc_upload_media_body(wp_user: str, wp_password: str, file_path: Path, bits_b64: str) -> str:
    mime_type = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<methodCall>
  <methodName>wp.uploadFile</methodName>
  <params>
    <param><value><int>1</int></value></param>
    <param><value><string>{xml_escape(wp_user)}</string></value></param>
    <param><value><string>{xml_escape(wp_password)}</string></value></param>
    <param><value><struct>
      <member><name>name</name><value><string>{xml_escape(file_path.name)}</string></value></member>
      <member><name>type</name><value><string>{xml_escape(mime_type)}</string></value></member>
      <member><name>bits</name><value><base64>{bits_b64}</base64></value></member>
      <member><name>overwrite</name><value><boolean>1</boolean></value></member>
    </struct></value></param>
  </params>
</methodCall>"""


def upload_media_xmlrpc(domain: str, wp_user: str, wp_app_password: str, file_path: Path) -> dict[str, Any]:
    normalized_domain = normalize_domain(domain)
    xmlrpc_url = f"https://{normalized_domain}/xmlrpc.php"
    bits_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
    xml_body = _build_xmlrpc_upload_media_body(
        wp_user=wp_user,
        wp_password=sanitize_app_password(wp_app_password),
        file_path=file_path,
        bits_b64=bits_b64,
    )
    response = requests.post(
        xmlrpc_url,
        data=xml_body.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
        timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(f"WordPress media upload failed ({response.status_code}): {response.text[:300]}")

    root = ET.fromstring(response.text)
    fault = root.find(".//fault")
    if fault is not None:
        message = " ".join("".join(fault.itertext()).split())
        raise RuntimeError(f"WordPress media upload fault: {message}")

    values = root.findall(".//params/param/value/struct/member")
    result: dict[str, Any] = {}
    for member in values:
        key = member.findtext("name")
        value_node = member.find("value")
        value = "".join(value_node.itertext()).strip() if value_node is not None else ""
        if key:
            result[key] = value
    return result


def _build_xmlrpc_edit_post_thumbnail_body(
    wp_user: str, wp_password: str, post_id: int, attachment_id: int
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<methodCall>
  <methodName>wp.editPost</methodName>
  <params>
    <param><value><int>1</int></value></param>
    <param><value><string>{xml_escape(wp_user)}</string></value></param>
    <param><value><string>{xml_escape(wp_password)}</string></value></param>
    <param><value><int>{post_id}</int></value></param>
    <param><value><struct>
      <member><name>post_thumbnail</name><value><int>{attachment_id}</int></value></member>
    </struct></value></param>
  </params>
</methodCall>"""


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
        resp = requests.patch(
            url,
            auth=auth,
            headers=headers,
            json={"featured_media": attachment_id},
            timeout=20,
        )
        if resp.status_code in (200, 204):
            return
    except requests.RequestException:
        pass

    xmlrpc_url = f"https://{normalized_domain}/xmlrpc.php"
    xml_body = _build_xmlrpc_edit_post_thumbnail_body(
        wp_user=wp_user,
        wp_password=sanitize_app_password(wp_app_password),
        post_id=post_id,
        attachment_id=attachment_id,
    )
    response = requests.post(
        xmlrpc_url,
        data=xml_body.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
        timeout=20,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"WordPress set featured image failed ({response.status_code}): {response.text[:300]}"
        )
    root = ET.fromstring(response.text)
    fault = root.find(".//fault")
    if fault is not None:
        message = " ".join("".join(fault.itertext()).split())
        raise RuntimeError(f"WordPress XML-RPC fault (set featured image): {message}")


def post_to_wordpress_xmlrpc(
    domain: str, wp_user: str, wp_app_password: str, article: Article, status: str
) -> dict[str, Any]:
    normalized_domain = normalize_domain(domain)
    xmlrpc_url = f"https://{normalized_domain}/xmlrpc.php"
    xml_body = _build_xmlrpc_new_post_body(
        wp_user=wp_user,
        wp_password=sanitize_app_password(wp_app_password),
        article=article,
        status=status,
    )
    response = requests.post(
        xmlrpc_url,
        data=xml_body.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"WordPress XML-RPC failed ({response.status_code}): {response.text[:300]}")

    root = ET.fromstring(response.text)
    fault = root.find(".//fault")
    if fault is not None:
        message = " ".join("".join(fault.itertext()).split())
        raise RuntimeError(f"WordPress XML-RPC fault: {message}")

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

    me_url = build_wp_api_endpoint(domain, "wp/v2/users/me")
    me_resp = requests.get(me_url, auth=auth, headers=headers, timeout=20)
    if me_resp.status_code != 200:
        try:
            me_json = me_resp.json()
            err_code = me_json.get("code", "")
            err_message = me_json.get("message", "")
        except ValueError:
            err_code = ""
            err_message = me_resp.text[:200]
        if err_code == "rest_not_logged_in":
            return post_to_wordpress_xmlrpc(domain, wp_user, wp_app_password, article, status)
        raise RuntimeError(
            f"WordPress auth preflight failed ({me_resp.status_code}) [{err_code}] {err_message}. endpoint={me_url}"
        )

    response = requests.post(url, auth=auth, headers=headers, data=payload, timeout=30)
    if response.status_code != 201:
        if response.status_code in {401, 403}:
            try:
                err_json = response.json()
                err_code = err_json.get("code", "")
                err_message = err_json.get("message", "")
            except ValueError:
                err_code = ""
                err_message = response.text[:200]
            raise RuntimeError(
                f"WordPress auth/permission failed ({response.status_code}) [{err_code}] {err_message}. endpoint={url}"
            )
        raise RuntimeError(f"WordPress post failed ({response.status_code}) on {url}: {response.text[:300]}")
    return response.json()


def choose_public_url(domain: str, created: dict[str, Any]) -> tuple[str, str]:
    normalized_domain = normalize_domain(domain)
    post_id = created.get("id")
    pretty_link = str(created.get("link") or "").strip()
    fallback_link = f"https://{normalized_domain}/?p={post_id}"

    if not pretty_link:
        return fallback_link, fallback_link
    try:
        check = requests.get(pretty_link, timeout=10, allow_redirects=True)
        if check.status_code >= 400:
            return fallback_link, pretty_link
    except requests.RequestException:
        return fallback_link, pretty_link
    return fallback_link, pretty_link

