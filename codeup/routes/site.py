from __future__ import annotations

import io
import json
import re
import zipfile

from flask import Blueprint, jsonify, send_file, send_from_directory

from codeup.config import MAX_HTML_SIZE
from codeup.routes.helpers import safejson
from codeup.security import get_session_id, sanitize_hosted_html
from codeup.services.html_utils import (
    apply_audit_fixes,
    audit_html,
    is_safe_hosted_html_page,
    is_safe_hosted_source_asset,
    publish_page_plan,
    safe_page_filename,
    summarize_html_changes,
    wrap_html,
)
from codeup.services.project_explainer import build_export_artifacts
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
    if not pages and html.strip():
        current_page = str(body.get("current_page") or "home").strip() or "home"
        pages[current_page] = html
    if project_id and not pages:
        project = load_project(project_id)
        if project:
            pages = project.pages.copy()
    return pages, project_id


def _ensure_source_refs(html: str, has_css: bool, has_js: bool) -> str:
    doc = wrap_html(html)
    if has_css and not re.search(r'<link\b[^>]*href=["\'](?:\./)?style\.css["\']', doc, re.IGNORECASE):
        link = '\n<link rel="stylesheet" href="style.css">'
        doc = re.sub(r"</head\s*>", lambda _m: link + "\n</head>", doc, count=1, flags=re.IGNORECASE)
    if has_js and not re.search(r'<script\b[^>]*src=["\'](?:\./)?script\.js["\']', doc, re.IGNORECASE):
        script = '\n<script src="script.js" defer></script>'
        doc = re.sub(r"</body\s*>", lambda _m: script + "\n</body>", doc, count=1, flags=re.IGNORECASE)
    return doc


def _source_files_from_body(body: dict) -> dict[str, str] | None:
    raw_files = body.get("files")
    if not isinstance(raw_files, dict):
        return None

    html = str(raw_files.get("index.html") or raw_files.get("html") or body.get("html") or "")
    css = str(raw_files.get("style.css") or raw_files.get("css") or body.get("css") or "")
    js = str(raw_files.get("script.js") or raw_files.get("js") or body.get("js") or "")
    if not html.strip():
        return None

    html = _ensure_source_refs(html, bool(css.strip()), bool(js.strip()))
    return {"index.html": html, "style.css": css, "script.js": js}


def _source_assets_from_body(body: dict) -> dict[str, str]:
    raw_files = body.get("files") if isinstance(body.get("files"), dict) else {}
    css = str(raw_files.get("style.css") or raw_files.get("css") or body.get("css") or "")
    js = str(raw_files.get("script.js") or raw_files.get("js") or body.get("js") or "")
    assets = {}
    if css.strip():
        assets["style.css"] = css
    if js.strip():
        assets["script.js"] = js
    return assets


def _audit_from_body_or_project(body: dict, project_id: str | None = None) -> dict | None:
    audit = body.get("audit")
    if isinstance(audit, dict):
        return audit
    if project_id:
        project = load_project(project_id)
        if project and project.audit_history:
            latest = project.audit_history[-1]
            if isinstance(latest, dict) and isinstance(latest.get("audit"), dict):
                return latest["audit"]
    return None


def _readme_text(name: str, files: list[str], project_type: str = "") -> str:
    title = (name or "CodeUp Web export").strip() or "CodeUp Web export"
    listed = "\n".join(f"- {filename}" for filename in files)
    type_line = f"Project type: {project_type}\n\n" if project_type else ""
    return (
        f"{title}\n\n"
        "This ZIP was exported from CodeUp Web, an accessibility-first website builder.\n\n"
        f"{type_line}"
        "Files included:\n"
        f"{listed}\n\n"
        "Learning artifacts include CODE_MAP.txt, STEP_NARRATION.txt, LEARNING_NOTES.txt, "
        "PROJECT_SUMMARY.txt, ACCESSIBILITY_REPORT.txt, PROJECT_REVIEW.txt, PREVIEW_DESCRIPTION.txt, "
        "TRAINER_NOTES.txt, STUDENT_RECAP.txt, and SCREEN_READER_SUMMARY.txt. CHANGE_REPLAY.txt is "
        "included when you edited the project, and BOOKMARKS.txt when you saved bookmarks.\n\n"
        "Open index.html in a browser to view the website. Edit style.css for visual design "
        "and script.js for small interactive behavior. Keep headings, labels, alt text, and "
        "keyboard focus styles when you make changes.\n"
    )


def _audit_report_text(audit: dict | None) -> str:
    if not audit:
        return ""
    lines = [f"Accessibility score: {audit.get('score', 'unknown')}/100", ""]
    issues = audit.get("issues") if isinstance(audit.get("issues"), list) else []
    if not issues:
        lines.append("No structured issues were reported in the last audit.")
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        lines.extend(
            [
                f"Severity: {issue.get('severity', 'unknown')}",
                f"Issue: {issue.get('description', issue.get('id', 'Unknown issue'))}",
                f"Why it matters: {issue.get('why_matters', 'This can make the website harder to use.')}",
                f"Suggested fix: {issue.get('suggested_fix', 'Review and improve this item.')}",
                "",
            ]
        )
    suggestions = audit.get("suggestions") if isinstance(audit.get("suggestions"), list) else []
    if suggestions:
        lines.append("Suggestions:")
        lines.extend(f"- {item}" for item in suggestions)
    return "\n".join(lines).strip() + "\n"


def _provided_artifacts_from_body(body: dict) -> dict[str, str]:
    keys = (
        "code_map",
        "step_narration",
        "learning_notes",
        "project_summary",
        "accessibility_map",
        "project_review",
        "preview_description",
        "trainer_notes",
        "student_recap",
        "screen_reader_summary",
        "run_summary",
        "debug_report",
        "screen_reader_tour",
        "keyboard_test",
        "visual_description",
        "readiness_score",
        "teacher_review",
        "pilot_report",
        "version_history",
        "instruction",
    )
    provided = {key: str(body.get(key) or "") for key in keys if str(body.get(key) or "").strip()}

    replay = body.get("change_replay")
    if isinstance(replay, str) and replay.strip():
        provided["change_replay"] = replay
    return provided


def _collect_export_artifacts(body: dict, source_files: dict[str, str], audit: dict | None) -> dict[str, str]:
    html = source_files.get("index.html") or next(iter(source_files.values()), "")
    css = source_files.get("style.css", "")
    js = source_files.get("script.js", "")
    raw_commands = body.get("commands")
    commands = [str(item) for item in raw_commands] if isinstance(raw_commands, list) else None
    replay = body.get("change_replay")
    change_replay = replay if isinstance(replay, dict) else None
    bookmarks = body.get("bookmarks")
    version_history = body.get("versions") if isinstance(body.get("versions"), list) else None
    artifacts = build_export_artifacts(
        html,
        css,
        js,
        name=str(body.get("name") or "CodeUp Web export"),
        project_type=str(body.get("project_type") or ""),
        audit=audit,
        provided=_provided_artifacts_from_body(body),
        commands=commands,
        change_replay=change_replay,
        bookmarks=bookmarks,
        version_history=version_history,
    )
    if audit:
        artifacts["ACCESSIBILITY_REPORT.txt"] = (
            artifacts["ACCESSIBILITY_REPORT.txt"].rstrip() + "\n\nDETAILED AUDIT\n\n" + _audit_report_text(audit)
        )
    return artifacts


def _write_export_artifacts(bundle: zipfile.ZipFile, artifacts: dict[str, str]) -> None:
    for filename, content in artifacts.items():
        bundle.writestr(filename, content)


@site_bp.route("/publish-site", methods=["POST"])
def publish_site():
    body = safejson()
    pages, project_id = _pages_from_body(body)
    source_assets = _source_assets_from_body(body)
    total_size = sum(len(page_html) for page_html in pages.values()) + sum(
        len(value) for value in source_assets.values()
    )
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
    intended_filenames = {filename for _, filename, _ in plan} | set(source_assets)
    delete_stale_hosted_pages(session_id, intended_filenames)
    page_urls = {}
    last_html = ""
    all_warnings: list[str] = []
    for name, filename, page_html in plan:
        wrapped, warnings = sanitize_hosted_html(wrap_html(page_html))
        all_warnings.extend(warnings)
        write_student_page(session_id, filename, wrapped)
        page_urls[name] = f"/student-site/{session_id}/{'' if filename == 'index.html' else filename}"
        if filename == "index.html" or not last_html:
            last_html = wrapped
    for filename, content in source_assets.items():
        write_student_page(session_id, filename, content)

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
    result: dict = {"success": True, "url": url, "pages": page_urls}
    if all_warnings:
        result["warnings"] = all_warnings
    return jsonify(result)


@site_bp.route("/student-site/<session_id>/")
def student_site(session_id: str):
    from codeup.security import sanitize_id

    return send_from_directory(student_site_path(sanitize_id(session_id)), "index.html")


@site_bp.route("/student-site/<session_id>/<path:filename>")
def student_site_page(session_id: str, filename: str):
    from codeup.security import sanitize_id

    if not (is_safe_hosted_html_page(filename) or is_safe_hosted_source_asset(filename)):
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
    source_files = _source_files_from_body(body)
    project_id = str(body.get("project_id") or "").strip() or None
    audit = _audit_from_body_or_project(body, project_id)
    if source_files:
        total_size = sum(len(value) for value in source_files.values())
        if total_size > MAX_HTML_SIZE * 5:
            return jsonify({"success": False, "error": f"Project too large (max {MAX_HTML_SIZE * 5} bytes)"}), 413
        project_type = str(body.get("project_type") or "")
        artifacts = _collect_export_artifacts(body, source_files, audit)
        artifact_files = list(artifacts)
        archive = io.BytesIO()
        manifest = {
            "project_id": project_id or "",
            "files": list(source_files),
            "entry": "index.html",
            "project_type": project_type,
            "artifacts": artifact_files,
        }
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for filename, content in source_files.items():
                bundle.writestr(filename, content)
            bundle.writestr(
                "README.txt",
                _readme_text(
                    str(body.get("name") or "CodeUp Web export"),
                    [*list(source_files), *artifact_files, "manifest.json"],
                    project_type,
                ),
            )
            _write_export_artifacts(bundle, artifacts)
            bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.seek(0)
        filename = safe_page_filename(str(body.get("name") or "codeup-site"))[:-5] + ".zip"
        append_memory(get_session_id(), note="Exported website ZIP")
        return send_file(
            archive,
            mimetype="application/zip",
            as_attachment=True,
            download_name=filename,
            max_age=0,
        )

    pages, project_id = _pages_from_body(body)
    audit = _audit_from_body_or_project(body, project_id)
    if not pages:
        return jsonify({"success": False, "error": "No pages to export"}), 400
    plan, collisions = publish_page_plan(pages)
    if collisions:
        details = "; ".join(f"{filename}: {', '.join(names)}" for filename, names in sorted(collisions.items()))
        return jsonify({"success": False, "error": f"Page names collide after slug normalization ({details})"}), 400
    archive = io.BytesIO()
    project_type = str(body.get("project_type") or "")
    manifest = {
        "project_id": project_id or "",
        "pages": {name: filename for name, filename, _ in plan},
        "project_type": project_type,
        "artifacts": [],
    }
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        exported_files = []
        artifact_source_files: dict[str, str] = {}
        for _, filename, page_html in plan:
            if len(page_html) > MAX_HTML_SIZE:
                return jsonify({"success": False, "error": f"Page {filename} too large"}), 413
            sanitized, _warnings = sanitize_hosted_html(wrap_html(page_html))
            bundle.writestr(filename, sanitized)
            exported_files.append(filename)
            if not artifact_source_files:
                artifact_source_files["index.html"] = sanitized
        artifacts = _collect_export_artifacts(body, artifact_source_files, audit)
        artifact_files = list(artifacts)
        manifest["artifacts"] = artifact_files
        bundle.writestr(
            "README.txt",
            _readme_text(
                str(body.get("name") or "CodeUp Web export"),
                [*exported_files, *artifact_files, "manifest.json"],
                project_type,
            ),
        )
        _write_export_artifacts(bundle, artifacts)
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
    archive.seek(0)
    filename = safe_page_filename(str(body.get("name") or "codeup-site"))[:-5] + ".zip"
    append_memory(get_session_id(), note="Exported website ZIP")
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
