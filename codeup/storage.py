"""Storage abstraction layer for session data and student sites.

Decouples the backend from raw JSON file operations so the storage
backend can be swapped (e.g. to a database) without changing callers.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from typing import Any

import codeup.config as _config
from codeup.models import HtmlMemory

_memory_locks: dict[str, threading.RLock] = {}
_memory_locks_guard = threading.Lock()


def _get_data_dir() -> str:
    return _config.DATA_DIR


def _data_path(*parts: str) -> str:
    path = os.path.join(_get_data_dir(), *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def memory_lock(session_id: str) -> threading.RLock:
    with _memory_locks_guard:
        lock = _memory_locks.get(session_id)
        if lock is None:
            lock = threading.RLock()
            _memory_locks[session_id] = lock
        return lock


# --- HTML memory ---


def _html_memory_path(session_id: str) -> str:
    return _data_path("html_memory", f"{session_id}.json")


def load_html_memory(session_id: str) -> HtmlMemory:
    path = _html_memory_path(session_id)
    if not os.path.exists(path):
        return HtmlMemory()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return HtmlMemory.from_dict(data)
    except Exception:
        return HtmlMemory()


def save_html_memory(memory: HtmlMemory, session_id: str) -> None:
    memory.history = memory.history[-30:]
    path = _html_memory_path(session_id)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(memory.to_dict(), handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


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


# --- Student sites ---


def student_site_path(session_id: str) -> str:
    return os.path.join(_get_data_dir(), "student_sites", session_id)


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


# --- Cleanup / retention ---


def cleanup_expired_sessions() -> int:
    """Remove session artifacts older than SESSION_ARTIFACT_MAX_AGE_SECONDS.

    Returns the number of sessions cleaned up.
    """
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
