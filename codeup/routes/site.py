"""Site publish, preview, audit, and reset routes."""

from __future__ import annotations

import io
import json
import zipfile

from flask import Blueprint, jsonify, send_file, send_from_directory

from codeup.config import MAX_HTML_SIZE
from codeup.routes.helpers import safejson
from codeup.security import get_session_id, sanitize_hosted_html
from codeup.services.html_utils import (
    apply_audit_fixes,
    audit_html,
    is_safe_hosted_html_page,
    publish_page_plan,
    safe_page_filename,
    summarize_html_changes,
    wrap_html,
)
from codeup.storage import (
    append_memory,
    append_project_audit,
    create_project_version,
    delete_stale_hosted_pages,
    load_html_memory,
    load_project,
    memory_lock,
    remove_html_memory_file,
    remove_student_site,
    student_site_path,
    write_student_page,
)

site_bp = Blueprint("site", __name__)


def _pages_from_body(body: dict) -> tuple[dict[str, str], str | None]:
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
    project_id = str(body.get("project_id") or "").strip() or None
    if project_id and not pages:
        project = load_project(project_id)
        if project:
            pages = project.pages.copy()
    if not pages and html.strip():
        pages["home"] = html
    return pages, project_id


@site_bp.route("/publish-site", methods=["POST"])
def publish_site():
    body = safejson()
    pages, project_id = _pages_from_body(body)
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
    if project_id:
        create_project_version(
            project_id,
            label="Published preview",
            source="publish",
            pages=pages,
            current_page=str(body.get("current_page") or "home"),
            summary=[f"Published {len(pages)} page(s) locally."],
        )
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
    body = safejson()
    html = str(body.get("html") or "")
    project_id = str(body.get("project_id") or "").strip()
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    audit = audit_html(html)
    append_memory(get_session_id(), note=f"Accessibility audit score {audit.score}", html=html)
    if project_id:
        append_project_audit(project_id, audit.to_dict())
    return jsonify({"success": True, "audit": audit.to_dict()})


@site_bp.route("/audit-autofix", methods=["POST"])
def audit_autofix():
    body = safejson()
    html = str(body.get("html") or "")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty", "code": ""}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)", "code": ""}), 413
    project_id = str(body.get("project_id") or "").strip()
    issue_id = str(body.get("issue_id") or "").strip() or None
    fix_all = bool(body.get("fix_all"))
    if project_id:
        create_project_version(
            project_id,
            label="Before audit autofix",
            source="audit-autofix-before",
            html=html,
            current_page=str(body.get("current_page") or "home"),
            summary=["Snapshot before audit autofix."],
        )
    fixed_html, fixed_ids, audit = apply_audit_fixes(html, issue_id=issue_id, fix_all=fix_all)
    summary = summarize_html_changes(html, fixed_html)
    append_memory(get_session_id(), note=f"Applied audit fixes: {', '.join(fixed_ids) or 'none'}", html=fixed_html)
    if project_id:
        create_project_version(
            project_id,
            label="Applied audit autofix",
            source="audit-autofix-after",
            html=fixed_html,
            current_page=str(body.get("current_page") or "home"),
            summary=summary,
        )
        append_project_audit(project_id, audit.to_dict())
    return jsonify(
        {
            "success": True,
            "code": fixed_html,
            "fixed": fixed_ids,
            "audit": audit.to_dict(),
            "summary": summary,
        }
    )


@site_bp.route("/export-site.zip", methods=["POST"])
def export_site_zip():
    body = safejson()
    pages, project_id = _pages_from_body(body)
    if not pages:
        return jsonify({"success": False, "error": "No pages to export"}), 400
    plan, collisions = publish_page_plan(pages)
    if collisions:
        details = "; ".join(f"{filename}: {', '.join(names)}" for filename, names in sorted(collisions.items()))
        return jsonify({"success": False, "error": f"Page names collide after slug normalization ({details})"}), 400
    archive = io.BytesIO()
    manifest = {
        "project_id": project_id or "",
        "pages": {name: filename for name, filename, _ in plan},
    }
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for _, filename, page_html in plan:
            if len(page_html) > MAX_HTML_SIZE:
                return jsonify({"success": False, "error": f"Page {filename} too large"}), 413
            bundle.writestr(filename, sanitize_hosted_html(wrap_html(page_html)))
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
    archive.seek(0)
    filename = safe_page_filename(str(body.get("name") or "codeup-site"))[:-5] + ".zip"
    return send_file(
        archive,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@site_bp.route("/reset-session", methods=["POST"])
def reset_session():
    session_id = get_session_id()
    with memory_lock(session_id):
        remove_html_memory_file(session_id)
        remove_student_site(session_id)
        memory = load_html_memory(session_id)
    return jsonify({"success": True, "memory": memory.to_dict()})
