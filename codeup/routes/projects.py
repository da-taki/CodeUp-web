from __future__ import annotations

from flask import Blueprint, jsonify, request

from codeup.config import MAX_HTML_SIZE
from codeup.routes.helpers import safejson
from codeup.storage import (
    create_project,
    create_project_version,
    duplicate_project,
    list_projects,
    load_project,
    restore_project_version,
    update_project,
)

projects_bp = Blueprint("projects", __name__)


def _project_payload() -> tuple[str, dict[str, str], str, str]:
    body = safejson()
    html = str(body.get("html") or "")
    raw_pages = body.get("pages")
    pages = {}
    if isinstance(raw_pages, dict):
        pages = {str(key): str(value or "") for key, value in raw_pages.items() if str(value or "").strip()}
    total_size = len(html) + sum(len(value) for value in pages.values())
    if total_size > MAX_HTML_SIZE * 5:
        raise ValueError(f"Project too large (max {MAX_HTML_SIZE * 5} bytes)")
    name = str(body.get("name") or "Untitled Project").strip()
    current_page = str(body.get("current_page") or "home").strip() or "home"
    return name, pages, html, current_page


@projects_bp.route("/projects", methods=["GET"])
def projects_index():
    return jsonify({"success": True, "projects": list_projects()})


@projects_bp.route("/projects", methods=["POST"])
def projects_create():
    try:
        name, pages, html, current_page = _project_payload()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    project = create_project(name, pages=pages, html=html, current_page=current_page)
    return jsonify({"success": True, "project": project.to_dict()}), 201


@projects_bp.route("/projects/<project_id>", methods=["GET"])
def projects_show(project_id: str):
    project = load_project(project_id)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404
    return jsonify({"success": True, "project": project.to_dict()})


@projects_bp.route("/projects/<project_id>", methods=["PATCH"])
def projects_update(project_id: str):
    body = safejson()
    name = str(body.get("name")).strip() if "name" in body else None
    raw_pages = body.get("pages")
    pages = {str(key): str(value or "") for key, value in raw_pages.items()} if isinstance(raw_pages, dict) else None
    html = str(body.get("html") or "")
    if len(html) + sum(len(value) for value in (pages or {}).values()) > MAX_HTML_SIZE * 5:
        return jsonify({"success": False, "error": f"Project too large (max {MAX_HTML_SIZE * 5} bytes)"}), 413
    project = update_project(
        project_id,
        name=name,
        pages=pages,
        html=html,
        current_page=str(body.get("current_page") or "") or None,
    )
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404
    return jsonify({"success": True, "project": project.to_dict()})


@projects_bp.route("/projects/<project_id>/autosave", methods=["POST"])
def projects_autosave(project_id: str):
    body = safejson()
    raw_pages = body.get("pages")
    pages = {str(key): str(value or "") for key, value in raw_pages.items()} if isinstance(raw_pages, dict) else None
    html = str(body.get("html") or "")
    project = update_project(
        project_id,
        pages=pages,
        html=html,
        current_page=str(body.get("current_page") or "") or None,
    )
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404
    return jsonify({"success": True, "project": project.to_dict()})


@projects_bp.route("/projects/<project_id>/duplicate", methods=["POST"])
def projects_duplicate(project_id: str):
    name = str(safejson().get("name") or "").strip() or None
    project = duplicate_project(project_id, name=name)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404
    return jsonify({"success": True, "project": project.to_dict()}), 201


@projects_bp.route("/projects/<project_id>/versions", methods=["GET", "POST"])
def project_versions(project_id: str):
    project = load_project(project_id)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404
    return _project_versions_dispatch(project_id, project)


def _project_versions_dispatch(project_id: str, project):
    if request.method == "GET":
        return jsonify({"success": True, "versions": [version.to_dict() for version in project.versions]})
    body = safejson()
    raw_pages = body.get("pages")
    pages = {str(key): str(value or "") for key, value in raw_pages.items()} if isinstance(raw_pages, dict) else None
    version = create_project_version(
        project_id,
        label=str(body.get("label") or "Saved version"),
        source=str(body.get("source") or "manual"),
        pages=pages,
        html=str(body.get("html") or ""),
        current_page=str(body.get("current_page") or project.current_page or "home"),
        summary=[str(item) for item in body.get("summary", [])] if isinstance(body.get("summary"), list) else [],
    )
    if not version:
        return jsonify({"success": False, "error": "Project not found"}), 404
    return jsonify({"success": True, "version": version.to_dict()}), 201


@projects_bp.route("/projects/<project_id>/versions/<version_id>/restore", methods=["POST"])
def project_versions_restore(project_id: str, version_id: str):
    project = restore_project_version(project_id, version_id)
    if not project:
        return jsonify({"success": False, "error": "Project or version not found"}), 404
    return jsonify({"success": True, "project": project.to_dict()})
