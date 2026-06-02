from __future__ import annotations

from flask import Blueprint, jsonify

from codeup.config import MAX_HTML_SIZE
from codeup.routes.helpers import safejson
from codeup.services.walkthrough import (
    compare_before_after,
    explain_watchpoint,
    fix_current_issue,
    keyboard_journey_move,
    keyboard_journey_start,
    list_watchpoints,
    page_map,
)

walkthrough_bp = Blueprint("walkthrough", __name__)


@walkthrough_bp.route("/walkthrough/page-map", methods=["POST"])
def walkthrough_page_map():
    body = safejson()
    html = str(body.get("html") or "")
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    result = page_map(html)
    return jsonify({"success": True, **result})


@walkthrough_bp.route("/walkthrough/keyboard-journey", methods=["POST"])
def walkthrough_keyboard_journey():
    body = safejson()
    html = str(body.get("html") or "")
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    result = keyboard_journey_start(html)
    return jsonify({"success": True, **result})


@walkthrough_bp.route("/walkthrough/keyboard-move", methods=["POST"])
def walkthrough_keyboard_move():
    body = safejson()
    html = str(body.get("html") or "")
    current_index = int(body.get("index", 0))
    direction = str(body.get("direction", "next"))
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    result = keyboard_journey_move(html, current_index, direction)
    return jsonify({"success": True, **result})


@walkthrough_bp.route("/walkthrough/watchpoints", methods=["POST"])
def walkthrough_watchpoints():
    body = safejson()
    html = str(body.get("html") or "")
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    result = list_watchpoints(html)
    return jsonify({"success": True, **result})


@walkthrough_bp.route("/walkthrough/explain", methods=["POST"])
def walkthrough_explain():
    body = safejson()
    html = str(body.get("html") or "")
    issue_index = int(body.get("issue_index", 0))
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    result = explain_watchpoint(html, issue_index)
    return jsonify({"success": True, **result})


@walkthrough_bp.route("/walkthrough/fix", methods=["POST"])
def walkthrough_fix():
    body = safejson()
    html = str(body.get("html") or "")
    issue_index = int(body.get("issue_index", 0))
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    result = fix_current_issue(html, issue_index)
    return jsonify({"success": True, **result})


@walkthrough_bp.route("/walkthrough/compare", methods=["POST"])
def walkthrough_compare():
    body = safejson()
    html_before = str(body.get("html_before") or "")
    html_after = str(body.get("html_after") or "")
    if len(html_before) > MAX_HTML_SIZE or len(html_after) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    result = compare_before_after(html_before, html_after)
    return jsonify({"success": True, **result})
