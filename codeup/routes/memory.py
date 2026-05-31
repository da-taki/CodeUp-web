"""Memory routes: html-memory, smart-memory, build-context."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from codeup.config import MAX_HTML_SIZE
from codeup.routes.helpers import safejson
from codeup.security import get_session_id
from codeup.services.memory_service import build_context, store_smart_memory
from codeup.storage import append_memory, load_html_memory

memory_bp = Blueprint("memory", __name__)


@memory_bp.route("/html-memory", methods=["GET", "POST"])
def html_memory():
    if request.method == "GET":
        session_id = get_session_id()
        return jsonify({"success": True, "memory": load_html_memory(session_id).to_dict()})

    body = safejson()
    html = str(body.get("html") or "")
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    session_id = get_session_id()
    memory = append_memory(
        session_id,
        prompt=str(body.get("prompt") or "").strip(),
        note=str(body.get("note") or "").strip(),
        html=html,
        url=str(body.get("url") or "").strip(),
    )
    return jsonify({"success": True, "memory": memory})


@memory_bp.route("/smart-memory", methods=["GET", "POST"])
def smart_memory_route():
    session_id = get_session_id()
    if request.method == "GET":
        memory = load_html_memory(session_id)
        return jsonify(
            {
                "success": True,
                "smart_memory": memory.smart_memory,
                "context": build_context(session_id, ""),
            }
        )

    body = safejson()
    content = str(body.get("content") or "").strip()
    memory_type = str(body.get("type") or "context").strip()
    if not content:
        return jsonify({"success": False, "error": "Content cannot be empty"}), 400
    if len(content) > 1000:
        return jsonify({"success": False, "error": "Content too large"}), 413

    memory = store_smart_memory(session_id, content, memory_type)
    return jsonify({"success": True, "smart_memory": memory.get("smart_memory", [])})


@memory_bp.route("/build-context", methods=["POST"])
def build_context_route():
    body = safejson()
    user_input = str(body.get("input") or "").strip()
    session_id = get_session_id()
    context = build_context(session_id, user_input)
    return jsonify({"success": True, "context": context})
