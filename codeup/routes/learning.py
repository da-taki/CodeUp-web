from __future__ import annotations

from flask import Blueprint, jsonify

from codeup.config import MAX_HTML_SIZE
from codeup.routes.helpers import safejson
from codeup.services.web_learning import (
    build_code_map,
    explain_beginner_errors,
    mistake_replay,
    tutorial_modules,
    validate_tutorial_step,
    watchpoint_pause,
)

learning_bp = Blueprint("learning", __name__)


def _sources() -> tuple[str, str, str]:
    body = safejson()
    html = str(body.get("html") or "")
    css = str(body.get("css") or "")
    js = str(body.get("js") or "")
    if len(html) + len(css) + len(js) > MAX_HTML_SIZE * 5:
        raise ValueError(f"Project too large (max {MAX_HTML_SIZE * 5} bytes)")
    return html, css, js


@learning_bp.route("/tutorial/modules", methods=["GET"])
def tutorial_modules_route():
    return jsonify({"success": True, "modules": tutorial_modules()})


@learning_bp.route("/tutorial/validate", methods=["POST"])
def tutorial_validate_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    module_id = str(body.get("module") or "")
    return jsonify({"success": True, **validate_tutorial_step(module_id, html, css, js)})


@learning_bp.route("/code-map", methods=["POST"])
def code_map_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    query = str(body.get("query") or "")
    return jsonify({"success": True, **build_code_map(html, css, js, query)})


@learning_bp.route("/mistake-replay", methods=["POST"])
def mistake_replay_route():
    body = safejson()
    total = sum(
        len(str(body.get(key) or ""))
        for key in ("html_before", "html_after", "css_before", "css_after", "js_before", "js_after")
    )
    if total > MAX_HTML_SIZE * 10:
        return jsonify({"success": False, "error": f"Comparison too large (max {MAX_HTML_SIZE * 10} bytes)"}), 413
    return jsonify(
        {
            "success": True,
            **mistake_replay(
                html_before=str(body.get("html_before") or ""),
                html_after=str(body.get("html_after") or ""),
                css_before=str(body.get("css_before") or ""),
                css_after=str(body.get("css_after") or ""),
                js_before=str(body.get("js_before") or ""),
                js_after=str(body.get("js_after") or ""),
            ),
        }
    )


@learning_bp.route("/watchpoints/check", methods=["POST"])
def watchpoints_check_route():
    body = safejson()
    html = str(body.get("html") or "")
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    raw = body.get("enabled")
    enabled = [str(item) for item in raw] if isinstance(raw, list) else ["all"]
    return jsonify({"success": True, **watchpoint_pause(html, enabled)})


@learning_bp.route("/explain-errors", methods=["POST"])
def explain_errors_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    return jsonify({"success": True, **explain_beginner_errors(html, css, js)})
