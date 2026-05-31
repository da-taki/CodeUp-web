"""Core routes: home, healthz, voice-command."""

from __future__ import annotations

import re

from flask import Blueprint, jsonify, render_template

from codeup.config import __version__
from codeup.routes.helpers import safejson

core_bp = Blueprint("core", __name__)


@core_bp.route("/")
def home():
    return render_template("index.html")


@core_bp.route("/ide")
def ide():
    return render_template("index.html")


@core_bp.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok", "version": __version__})


@core_bp.route("/voice-command", methods=["POST"])
def voice_command():
    text = str(safejson().get("text") or "").strip()
    lower = text.lower()
    if not text:
        return jsonify({"success": True, "action": "unknown", "message": "No command heard"})
    if "wake word" in lower:
        action = "set_wake_word"
    elif (
        "next heading" in lower
        or "previous heading" in lower
        or "next section" in lower
        or "previous section" in lower
        or re.search(r"read paragraph\s+\d+", lower)
    ):
        action = "navigate_page"
    elif "high contrast" in lower:
        action = "edit_css"
    elif "contrast" in lower:
        action = "announce_contrast"
    elif "what is a div" in lower or "aria-label" in lower or "what does" in lower:
        action = "explain_concept"
    elif "go back" in lower or lower.startswith("undo"):
        action = "undo_version"
    elif "what changed" in lower or "compare versions" in lower or "review changes" in lower:
        action = "review_changes"
    elif "multi page" in lower or "multiple page" in lower:
        action = "create_multipage_site"
    elif "go to page" in lower or "switch to page" in lower:
        action = "switch_page"
    elif "template" in lower:
        action = "use_template"
    elif (
        "make the heading" in lower
        or "make heading" in lower
        or "change the background" in lower
        or "background" in lower
        or "font" in lower
        or "text color" in lower
        or "more spacing" in lower
        or "less spacing" in lower
        or "rounded" in lower
        or "center" in lower
    ):
        action = "edit_css"
    elif "pause voice" in lower:
        action = "pause_voice"
    elif "resume voice" in lower or "voice on" in lower:
        action = "resume_voice"
    elif "stop speaking" in lower or "quiet" in lower:
        action = "stop_speaking"
    elif "preview" in lower or "show website" in lower:
        action = "preview_site"
    elif "audit" in lower or "accessibility" in lower:
        action = "audit_site"
    elif "outline" in lower or "page structure" in lower:
        action = "outline_site"
    elif "export" in lower or "download" in lower:
        action = "export_site"
    elif "reset session" in lower or lower == "reset":
        action = "reset_session"
    elif "add that" in lower or "apply that" in lower or "fix missing" in lower:
        action = "apply_review"
    elif "missing" in lower or "review" in lower or "what do you think" in lower:
        action = "review_site"
    elif "explain" in lower or "describe" in lower:
        action = "explain_site"
    elif "sonify" in lower or "sound" in lower:
        action = "sonify_site"
    elif re.search(r"\b(build|make|create|generate)\b.*\b(website|site|page)\b", lower):
        action = "build_site"
    else:
        action = "chat"
    return jsonify({"success": True, "action": action, "text": text})
