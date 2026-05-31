from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from codeup.config import __version__
from codeup.routes.helpers import safejson
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
