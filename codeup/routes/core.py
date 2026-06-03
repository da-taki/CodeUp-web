from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from codeup.config import MAX_HTML_SIZE, MAX_MESSAGE_SIZE, __version__
from codeup.routes.helpers import safejson
from codeup.services.action_router import route_natural_command
from codeup.services.intent_router import route_intent

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
    routed = route_intent(text)
    data = routed.to_dict()
    data["success"] = True
    return jsonify(data)


@core_bp.route("/voice-action", methods=["POST"])
def voice_action():
    body = safejson()
    transcript = str(body.get("transcript") or "").strip()
    current_html = str(body.get("html") or "")
    language = str(body.get("language") or "en")

    if not transcript:
        return jsonify({"success": False, "error": "No transcript provided"}), 400
    if len(transcript) > MAX_MESSAGE_SIZE:
        return jsonify({"success": False, "error": "Transcript too large"}), 413
    if len(current_html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": "HTML too large"}), 413

    result = route_natural_command(transcript, current_html, language)
    if result is None:
        return jsonify({"success": False, "error": "Could not parse natural command. Try a simpler request."})

    return jsonify({"success": True, **result})
