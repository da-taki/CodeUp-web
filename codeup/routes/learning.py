from __future__ import annotations

from flask import Blueprint, jsonify

from codeup.config import MAX_HTML_SIZE
from codeup.routes.helpers import safejson
from codeup.services.guided_build import guided_recap, guided_steps, validate_guided_step
from codeup.services.project_explainer import (
    build_accessibility_map,
    build_file_explanation,
    build_landmarks_summary,
    build_learning_notes,
    build_pilot_report,
    build_preview_description,
    build_project_review,
    build_project_summary,
    build_screen_reader_summary,
    build_step_narration,
    build_student_recap,
    build_trainer_notes,
)
from codeup.services.selector_explainer import build_selector_explainer
from codeup.services.tutorial_modules import tutorial_tracks
from codeup.services.version_history import build_version_history_report
from codeup.services.web_learning import (
    build_code_map,
    explain_beginner_errors,
    mistake_replay,
    tutorial_modules,
    validate_tutorial_step,
    watchpoint_pause,
)
from codeup.services.website_accessibility_lab import (
    build_keyboard_test,
    build_readiness_report,
    build_readiness_score,
    build_screen_reader_tour,
    build_visual_description,
)
from codeup.services.website_debugger import apply_safe_js_fixes, build_debug_report, build_debug_teacher
from codeup.services.website_runner import NO_PROJECT_MESSAGE, build_run_summary, build_teacher_review
from codeup.services.website_runtime_teacher import build_runtime_teacher

learning_bp = Blueprint("learning", __name__)


def _sources() -> tuple[str, str, str]:
    body = safejson()
    html = str(body.get("html") or "")
    css = str(body.get("css") or "")
    js = str(body.get("js") or "")
    if len(html) + len(css) + len(js) > MAX_HTML_SIZE * 5:
        raise ValueError(f"Project too large (max {MAX_HTML_SIZE * 5} bytes)")
    return html, css, js


def _project_metadata(body: dict) -> dict:
    audit = body.get("audit") if isinstance(body.get("audit"), dict) else None
    return {
        "name": str(body.get("name") or body.get("project_name") or "CodeUp Web project"),
        "project_type": str(body.get("project_type") or "generic_website"),
        "audit": audit,
    }


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


@learning_bp.route("/project-code-map", methods=["POST"])
def project_code_map_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    query = str(body.get("query") or "")
    return jsonify({"success": True, **build_code_map(html, css, js, query)})


@learning_bp.route("/project-step-narration", methods=["POST"])
def project_step_narration_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    text = build_step_narration(html, css, js, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "step_narration": text})


@learning_bp.route("/project-file-explanation", methods=["POST"])
def project_file_explanation_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    metadata = _project_metadata(body)
    text = build_file_explanation(
        str(body.get("file") or "html"), html, css, js, name=metadata["name"], project_type=metadata["project_type"]
    )
    return jsonify({"success": True, "text": text, "explanation": text})


@learning_bp.route("/project-learning-notes", methods=["POST"])
def project_learning_notes_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    text = build_learning_notes(html, css, js, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "learning_notes": text})


@learning_bp.route("/project-accessibility-map", methods=["POST"])
def project_accessibility_map_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    text = build_accessibility_map(html, css, js, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "accessibility_map": text})


@learning_bp.route("/project-review", methods=["POST"])
def project_review_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    text = build_project_review(html, css, js, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "review": text})


@learning_bp.route("/preview-description", methods=["POST"])
def preview_description_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    metadata = _project_metadata(body)
    text = build_preview_description(html, css, js, name=metadata["name"], project_type=metadata["project_type"])
    return jsonify({"success": True, "text": text, "description": text})


@learning_bp.route("/project-summary", methods=["POST"])
def project_summary_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    text = build_project_summary(html, css, js, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "summary": text})


@learning_bp.route("/project-landmarks", methods=["POST"])
def project_landmarks_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    text = build_landmarks_summary(html, css, js, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "landmarks": text})


@learning_bp.route("/trainer-notes", methods=["POST"])
def trainer_notes_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    text = build_trainer_notes(html, css, js, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "trainer_notes": text})


@learning_bp.route("/student-recap", methods=["POST"])
def student_recap_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    raw_commands = body.get("commands")
    commands = [str(item) for item in raw_commands] if isinstance(raw_commands, list) else None
    text = build_student_recap(html, css, js, commands=commands, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "student_recap": text})


@learning_bp.route("/screen-reader-summary", methods=["POST"])
def screen_reader_summary_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    text = build_screen_reader_summary(html, css, js, **_project_metadata(body))
    return jsonify({"success": True, "text": text, "screen_reader_summary": text})


@learning_bp.route("/run-summary", methods=["POST"])
def run_summary_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    text = build_run_summary(html, css, js, **_project_metadata(safejson()))
    return jsonify({"success": True, "text": text, "run_summary": text})


@learning_bp.route("/debug-report", methods=["POST"])
def debug_report_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    report = build_debug_report(html, css, js)
    return jsonify({"success": True, "text": report["text"], "issues": report["issues"]})


@learning_bp.route("/debug-fix", methods=["POST"])
def debug_fix_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    result = apply_safe_js_fixes(html, css, js)
    return jsonify({"success": True, **result})


@learning_bp.route("/screen-reader-tour", methods=["POST"])
def screen_reader_tour_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    text = build_screen_reader_tour(html, css, js, **_project_metadata(safejson()))
    return jsonify({"success": True, "text": text, "screen_reader_tour": text})


@learning_bp.route("/keyboard-test", methods=["POST"])
def keyboard_test_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    text = build_keyboard_test(html, css, js, **_project_metadata(safejson()))
    return jsonify({"success": True, "text": text, "keyboard_test": text})


@learning_bp.route("/visual-description", methods=["POST"])
def visual_description_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    text = build_visual_description(html, css, js, **_project_metadata(safejson()))
    return jsonify({"success": True, "text": text, "visual_description": text})


@learning_bp.route("/readiness-score", methods=["POST"])
def readiness_score_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    text = build_readiness_score(html, css, js, **_project_metadata(safejson()))
    return jsonify({"success": True, "text": text, "readiness_score": text})


@learning_bp.route("/teacher-review", methods=["POST"])
def teacher_review_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    result = build_teacher_review(html, css, js, **_project_metadata(safejson()))
    return jsonify({"success": True, "text": result["text"], "suggestions": result["suggestions"]})


@learning_bp.route("/version-history", methods=["POST"])
def version_history_route():
    body = safejson()
    text = build_version_history_report(body.get("versions"))
    return jsonify({"success": True, "text": text, "version_history": text})


@learning_bp.route("/tutorial/tracks", methods=["GET"])
def tutorial_tracks_route():
    return jsonify({"success": True, "tracks": tutorial_tracks()})


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
                mode=str(body.get("mode") or "summary"),
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


@learning_bp.route("/website-runtime-teacher", methods=["POST"])
def website_runtime_teacher_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    result = build_runtime_teacher(html, css, js, **_project_metadata(safejson()))
    return jsonify(
        {"success": True, "text": result["text"], "speech": result.get("speech", ""), "facts": result["facts"]}
    )


@learning_bp.route("/website-debug-teacher", methods=["POST"])
def website_debug_teacher_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    result = build_debug_teacher(html, css, js)
    return jsonify(
        {"success": True, "text": result["text"], "speech": result.get("speech", ""), "issues": result["issues"]}
    )


@learning_bp.route("/selector-explainer", methods=["POST"])
def selector_explainer_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    query = str(body.get("query") or "")
    result = build_selector_explainer(html, css, js, query)
    return jsonify({"success": True, **result})


@learning_bp.route("/accessibility-readiness-score", methods=["POST"])
def accessibility_readiness_score_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    result = build_readiness_report(html, css, js, **_project_metadata(safejson()))
    return jsonify({"success": True, **result})


@learning_bp.route("/pilot-report", methods=["POST"])
def pilot_report_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    body = safejson()
    raw_commands = body.get("commands")
    commands = [str(item) for item in raw_commands] if isinstance(raw_commands, list) else None
    versions = body.get("versions") if isinstance(body.get("versions"), list) else None
    text = build_pilot_report(html, css, js, commands=commands, version_history=versions, **_project_metadata(body))
    speech = "Pilot report ready. The full report is on screen and will be included in your export."
    if text.strip().endswith(NO_PROJECT_MESSAGE):
        speech = NO_PROJECT_MESSAGE
    return jsonify({"success": True, "text": text, "speech": speech, "pilot_report": text})


@learning_bp.route("/guided-build/steps", methods=["GET"])
def guided_build_steps_route():
    return jsonify({"success": True, "steps": guided_steps()})


@learning_bp.route("/guided-build/validate", methods=["POST"])
def guided_build_validate_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    step_id = str(safejson().get("step") or "")
    return jsonify({"success": True, **validate_guided_step(step_id, html, css, js)})


@learning_bp.route("/guided-build/recap", methods=["POST"])
def guided_build_recap_route():
    try:
        html, css, js = _sources()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 413
    return jsonify({"success": True, **guided_recap(html, css, js)})
