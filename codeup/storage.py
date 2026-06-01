from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import codeup.config as _config
from codeup.models import HtmlMemory, Project, ProjectVersion

_memory_locks: dict[str, threading.RLock] = {}
_memory_locks_guard = threading.Lock()
_project_locks: dict[str, threading.RLock] = {}
_project_locks_guard = threading.Lock()

DATA_SUBDIRS = ("projects", "html_memory", "student_sites", "exports", "tmp")


def _get_data_dir() -> str:
    return os.path.abspath(_config.DATA_DIR)


def init_data_dirs() -> None:
    for subdir in DATA_SUBDIRS:
        os.makedirs(os.path.join(_get_data_dir(), subdir), exist_ok=True)


def _data_path(*parts: str) -> str:
    path = os.path.join(_get_data_dir(), *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _legacy_root_path(*parts: str) -> str:
    return os.path.join(str(_config.REPO_ROOT), *parts)


def _read_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _atomic_write_json(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def memory_lock(session_id: str) -> threading.RLock:
    with _memory_locks_guard:
        lock = _memory_locks.get(session_id)
        if lock is None:
            lock = threading.RLock()
            _memory_locks[session_id] = lock
        return lock


def project_lock(project_id: str) -> threading.RLock:
    with _project_locks_guard:
        lock = _project_locks.get(project_id)
        if lock is None:
            lock = threading.RLock()
            _project_locks[project_id] = lock
        return lock


def _html_memory_path(session_id: str) -> str:
    return _data_path("html_memory", f"{session_id}.json")


def _legacy_html_memory_path(session_id: str) -> str:
    return _legacy_root_path("html_memory", f"{session_id}.json")


def load_html_memory(session_id: str) -> HtmlMemory:
    path = _html_memory_path(session_id)
    legacy_path = _legacy_html_memory_path(session_id)
    source_path = path if os.path.exists(path) else legacy_path
    if not os.path.exists(source_path):
        return HtmlMemory()
    try:
        data = _read_json(source_path)
        if source_path == legacy_path and not os.path.exists(path):
            _atomic_write_json(path, data)
        return HtmlMemory.from_dict(data)
    except Exception:
        return HtmlMemory()


def save_html_memory(memory: HtmlMemory, session_id: str) -> None:
    memory.history = memory.history[-30:]
    path = _html_memory_path(session_id)
    _atomic_write_json(path, memory.to_dict())


def append_memory(
    session_id: str,
    prompt: str = "",
    note: str = "",
    html: str = "",
    url: str = "",
    review: str = "",
) -> dict[str, Any]:
    with memory_lock(session_id):
        memory = load_html_memory(session_id)
        if prompt or note or url:
            memory.history.append({"prompt": prompt, "note": note, "url": url, "timestamp": time.time()})
        if html:
            memory.last_html = html
        if url:
            memory.last_url = url
        if review:
            memory.last_review = review
        save_html_memory(memory, session_id)
        return memory.to_dict()


def student_site_path(session_id: str) -> str:
    return os.path.join(_get_data_dir(), "student_sites", session_id)


def exports_path() -> str:
    path = os.path.join(_get_data_dir(), "exports")
    os.makedirs(path, exist_ok=True)
    return path


def projects_path() -> str:
    path = os.path.join(_get_data_dir(), "projects")
    os.makedirs(path, exist_ok=True)
    return path


def ensure_student_site_dir(session_id: str) -> str:
    path = student_site_path(session_id)
    os.makedirs(path, exist_ok=True)
    return path


def write_student_page(session_id: str, filename: str, content: str) -> None:
    site_dir = ensure_student_site_dir(session_id)
    with open(os.path.join(site_dir, filename), "w", encoding="utf-8") as handle:
        handle.write(content)


def delete_stale_hosted_pages(session_id: str, intended_filenames: set[str]) -> None:
    from codeup.services.html_utils import is_safe_hosted_html_page

    site_dir = student_site_path(session_id)
    if not os.path.isdir(site_dir):
        return
    for existing in os.listdir(site_dir):
        if existing in intended_filenames or not is_safe_hosted_html_page(existing):
            continue
        candidate = os.path.join(site_dir, existing)
        if os.path.isfile(candidate):
            try:
                os.remove(candidate)
            except OSError:
                pass


def remove_student_site(session_id: str) -> None:
    site_dir = student_site_path(session_id)
    try:
        if os.path.isdir(site_dir):
            shutil.rmtree(site_dir)
    except OSError:
        pass


def remove_html_memory_file(session_id: str) -> None:
    path = _html_memory_path(session_id)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _project_path(project_id: str) -> str:
    from codeup.security import sanitize_id

    return _data_path("projects", f"{sanitize_id(project_id)}.json")


def _normalize_pages(pages: dict[str, Any] | None, html: str = "") -> dict[str, str]:
    normalized = {}
    if isinstance(pages, dict):
        for name, page_html in pages.items():
            key = str(name or "home").strip() or "home"
            value = str(page_html or "")
            if value.strip():
                normalized[key] = value
    if not normalized and html.strip():
        normalized["home"] = html
    return normalized


def create_project(
    name: str, pages: dict[str, Any] | None = None, html: str = "", current_page: str = "home"
) -> Project:
    now = _utc_now()
    project = Project(
        id=uuid.uuid4().hex,
        name=(name or "Untitled Project").strip()[:120] or "Untitled Project",
        created_at=now,
        updated_at=now,
        pages=_normalize_pages(pages, html),
        current_page=current_page or "home",
    )
    if project.pages:
        project.versions.append(
            ProjectVersion(
                id=uuid.uuid4().hex,
                timestamp=now,
                label="Initial version",
                source="create",
                pages=project.pages.copy(),
                current_page=project.current_page,
                summary=["Project created"],
            )
        )
    save_project(project)
    return project


def list_projects() -> list[dict[str, Any]]:
    directory = projects_path()
    projects = []
    for filename in os.listdir(directory):
        if not filename.endswith(".json"):
            continue
        project = load_project(filename[:-5])
        if not project:
            continue
        data = project.to_dict()
        data["versions"] = []
        data["version_count"] = len(project.versions)
        projects.append(data)
    return sorted(projects, key=lambda item: item.get("updated_at", ""), reverse=True)


def load_project(project_id: str) -> Project | None:
    path = _project_path(project_id)
    if not os.path.exists(path):
        return None
    try:
        project = Project.from_dict(_read_json(path))
        return project if project.id else None
    except Exception:
        return None


def save_project(project: Project) -> None:
    project.versions = project.versions[-_config.MAX_PROJECT_VERSIONS :]
    _atomic_write_json(_project_path(project.id), project.to_dict())


def update_project(
    project_id: str,
    *,
    name: str | None = None,
    pages: dict[str, Any] | None = None,
    html: str = "",
    current_page: str | None = None,
) -> Project | None:
    with project_lock(project_id):
        project = load_project(project_id)
        if not project:
            return None
        if name is not None:
            project.name = name.strip()[:120] or project.name
        normalized_pages = _normalize_pages(pages, html)
        if normalized_pages:
            project.pages = normalized_pages
        if current_page:
            project.current_page = current_page
        project.updated_at = _utc_now()
        save_project(project)
        return project


def duplicate_project(project_id: str, name: str | None = None) -> Project | None:
    source = load_project(project_id)
    if not source:
        return None
    duplicate = create_project(
        name or f"{source.name} Copy",
        pages=source.pages.copy(),
        current_page=source.current_page,
    )
    duplicate.audit_history = list(source.audit_history[-10:])
    save_project(duplicate)
    return duplicate


def create_project_version(
    project_id: str,
    *,
    label: str,
    source: str,
    pages: dict[str, Any] | None = None,
    html: str = "",
    current_page: str = "home",
    summary: list[str] | None = None,
) -> ProjectVersion | None:
    with project_lock(project_id):
        project = load_project(project_id)
        if not project:
            return None
        normalized_pages = _normalize_pages(pages, html)
        if not normalized_pages:
            normalized_pages = project.pages.copy()
        version = ProjectVersion(
            id=uuid.uuid4().hex,
            timestamp=_utc_now(),
            label=(label or "Saved version").strip()[:120] or "Saved version",
            source=(source or "manual").strip()[:80] or "manual",
            pages=normalized_pages,
            current_page=current_page or project.current_page or "home",
            summary=summary or [],
        )
        project.pages = normalized_pages
        project.current_page = version.current_page
        project.updated_at = version.timestamp
        project.versions.append(version)
        save_project(project)
        return version


def restore_project_version(project_id: str, version_id: str) -> Project | None:
    with project_lock(project_id):
        project = load_project(project_id)
        if not project:
            return None
        version = next((item for item in project.versions if item.id == version_id), None)
        if not version:
            return None
        project.pages = version.pages.copy()
        project.current_page = version.current_page or "home"
        project.updated_at = _utc_now()
        project.versions.append(
            ProjectVersion(
                id=uuid.uuid4().hex,
                timestamp=project.updated_at,
                label=f"Restored {version.label}",
                source="restore",
                pages=project.pages.copy(),
                current_page=project.current_page,
                summary=[f"Restored version {version.label}"],
            )
        )
        save_project(project)
        return project


def append_project_audit(project_id: str, audit: dict[str, Any]) -> Project | None:
    with project_lock(project_id):
        project = load_project(project_id)
        if not project:
            return None
        project.audit_history.append({"timestamp": _utc_now(), "audit": audit})
        project.audit_history = project.audit_history[-25:]
        project.updated_at = _utc_now()
        save_project(project)
        return project


def cleanup_expired_sessions() -> int:
    cutoff = time.time() - _config.SESSION_ARTIFACT_MAX_AGE_SECONDS
    cleaned = 0

    memory_dir = os.path.join(_get_data_dir(), "html_memory")
    if os.path.isdir(memory_dir):
        for filename in os.listdir(memory_dir):
            filepath = os.path.join(memory_dir, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    session_id = filename.replace(".json", "")
                    remove_student_site(session_id)
                    cleaned += 1
            except OSError:
                pass

    sites_dir = os.path.join(_get_data_dir(), "student_sites")
    if os.path.isdir(sites_dir):
        for dirname in os.listdir(sites_dir):
            dirpath = os.path.join(sites_dir, dirname)
            if not os.path.isdir(dirpath):
                continue
            try:
                if os.path.getmtime(dirpath) < cutoff:
                    shutil.rmtree(dirpath)
                    cleaned += 1
            except OSError:
                pass

    return cleaned
