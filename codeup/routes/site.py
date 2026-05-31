"""Site publish, preview, audit, and reset routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, send_from_directory

from codeup.config import MAX_HTML_SIZE
from codeup.routes.helpers import safejson
from codeup.security import get_session_id, sanitize_hosted_html
from codeup.services.html_utils import (
    audit_html,
    is_safe_hosted_html_page,
    publish_page_plan,
    wrap_html,
)
from codeup.storage import (
    append_memory,
    delete_stale_hosted_pages,
    load_html_memory,
    memory_lock,
    remove_html_memory_file,
    remove_student_site,
    student_site_path,
    write_student_page,
)

site_bp = Blueprint("site", __name__)


@site_bp.route("/publish-site", methods=["POST"])
def publish_site():
    body = safejson()
    html = str(body.get("html") or "")
    raw_pages = body.get("pages")
    pages: dict[str, str] = {}
    if isinstance(raw_pages, dict):
        for name, page_html in raw_pages.items():
            page_name = str(name or "page").strip() or "page"
            page_value = str(page_html or "")
            if not page_value.strip():
                continue
            pages[page_name] = page_value
    if not pages and html.strip():
        pages["home"] = html
    total_size = sum(len(page_html) for page_html in pages.values())
    if total_size > MAX_HTML_SIZE * 5:
        return jsonify({"success": False, "error": f"Website too large (max {MAX_HTML_SIZE * 5} bytes)"}), 413
    if not pages:
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400

    plan, collisions = publish_page_plan(pages)
    if collisions:
        details = "; ".join(f"{filename}: {', '.join(names)}" for filename, names in sorted(collisions.items()))
        return jsonify({"success": False, "error": f"Page names collide after slug normalization ({details})"}), 400

    for name, _, page_html in plan:
        if len(page_html) > MAX_HTML_SIZE:
            return jsonify({"success": False, "error": f"Page {name} too large (max {MAX_HTML_SIZE} bytes)"}), 413

    session_id = get_session_id()
    intended_filenames = {filename for _, filename, _ in plan}
    delete_stale_hosted_pages(session_id, intended_filenames)
    page_urls = {}
    last_html = ""
    for name, filename, page_html in plan:
        wrapped = sanitize_hosted_html(wrap_html(page_html))
        write_student_page(session_id, filename, wrapped)
        page_urls[name] = f"/student-site/{session_id}/{'' if filename == 'index.html' else filename}"
        if filename == "index.html" or not last_html:
            last_html = wrapped

    url = f"/student-site/{session_id}/"
    append_memory(session_id, note=f"Published website preview with {len(pages)} page(s)", html=last_html, url=url)
    return jsonify({"success": True, "url": url, "pages": page_urls})


@site_bp.route("/student-site/<session_id>/")
def student_site(session_id: str):
    from codeup.security import sanitize_id

    return send_from_directory(student_site_path(sanitize_id(session_id)), "index.html")


@site_bp.route("/student-site/<session_id>/<path:filename>")
def student_site_page(session_id: str, filename: str):
    from codeup.security import sanitize_id

    if not is_safe_hosted_html_page(filename):
        return jsonify({"success": False, "error": "Page not found"}), 404
    return send_from_directory(student_site_path(sanitize_id(session_id)), filename)


@site_bp.route("/html-audit", methods=["POST"])
def html_audit():
    html = str(safejson().get("html") or "")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    audit = audit_html(html)
    append_memory(get_session_id(), note=f"Accessibility audit score {audit.score}", html=html)
    return jsonify({"success": True, "audit": audit.to_dict()})


@site_bp.route("/reset-session", methods=["POST"])
def reset_session():
    session_id = get_session_id()
    with memory_lock(session_id):
        remove_html_memory_file(session_id)
        memory = load_html_memory(session_id)
    remove_student_site(session_id)
    return jsonify({"success": True, "memory": memory.to_dict()})
