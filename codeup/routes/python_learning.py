from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Any

from flask import Blueprint, jsonify

from codeup.routes.helpers import safejson
from codeup.security import get_session_id
from codeup.services.python_learning import (
    analyze_python_code,
    build_audio_code_map,
    build_state_watch_model,
    build_step_narration,
    check_conditional_breakpoints,
    evaluate_conditional_breakpoints,
    explain_error,
    explain_mistake_replay,
    explain_state_watch_step,
    parse_conditional_breakpoint,
    run_python_code,
    validate_python_code,
    watch_variables,
)

python_bp = Blueprint("python_learning", __name__)

_watched_lock = threading.RLock()
_watched_vars: dict[str, set[str]] = {}
_mistake_lock = threading.RLock()
_mistakes: dict[str, dict[str, Any]] = {}
_breakpoint_lock = threading.RLock()
_breakpoints: dict[str, list[dict[str, Any]]] = {}
_state_watch_lock = threading.RLock()
_state_watch: dict[str, dict[str, Any]] = {}


def _body_code(body: dict[str, Any]) -> str:
    return str(body.get("code") or body.get("python") or "")


def _body_inputs(body: dict[str, Any]) -> list[str] | None:
    raw = body.get("inputs")
    if not isinstance(raw, list):
        return None
    return [str(item) for item in raw]


def _state_key(code: str, inputs: list[str] | None) -> str:
    payload = json.dumps({"code": code, "inputs": inputs or []}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _session_watches(session_id: str) -> set[str]:
    with _watched_lock:
        return set(_watched_vars.get(session_id, set()))


def _session_breakpoints(session_id: str) -> list[dict[str, Any]]:
    with _breakpoint_lock:
        return [dict(item) for item in _breakpoints.get(session_id, [])]


def _record_run(session_id: str, code: str, result: dict[str, Any]) -> None:
    with _mistake_lock:
        snap = dict(_mistakes.get(session_id, {}))
        if not result.get("success") and result.get("error"):
            snap["error_code"] = code
            snap["error_msg"] = result.get("error", "")
            snap["error_explanation"] = result.get("explanation", "")
        elif result.get("success") and snap.get("error_code"):
            snap["success_code"] = code
            snap["success_output"] = result.get("output", "")
        _mistakes[session_id] = snap


@python_bp.route("/python/run", methods=["POST"])
def python_run_route():
    body = safejson()
    code = _body_code(body)
    session_id = get_session_id()
    result = run_python_code(code, inputs=_body_inputs(body))
    if result.get("success"):
        breakpoint_check = evaluate_conditional_breakpoints(
            result.get("trace") or [], _session_breakpoints(session_id), code=code
        )
        if breakpoint_check.get("triggered"):
            result["breakpoint"] = breakpoint_check
            result["speech"] = breakpoint_check.get("speech") or result.get("speech", "")
    _record_run(session_id, code, result)
    status = 200
    error_text = str(result.get("error", "")).lower()
    if not result.get("success"):
        # A timeout is an execution outcome (the program ran but did not finish in time),
        # not a payload-size problem, so it stays 200 like syntax and runtime errors. Its
        # message contains "too long" ("ran for too long"), so it is excluded before the
        # size-limit check below, which is reserved for oversized source or output.
        if "timed out" in error_text:
            status = 200
        elif "too large" in error_text or "too long" in error_text:
            status = 413
        elif "too many queued inputs" in error_text:
            status = 400
        elif "cannot be empty" in error_text:
            status = 400
    return jsonify({**result, "auto_speak": True}), status


@python_bp.route("/python/conditional-breakpoint", methods=["POST"])
def python_conditional_breakpoint_route():
    body = safejson()
    session_id = get_session_id()
    action = str(body.get("action") or "check").strip().lower()
    code = _body_code(body)
    inputs = _body_inputs(body)

    if action in {"list", "show"}:
        breakpoints = _session_breakpoints(session_id)
        msg = (
            "Conditional audio breakpoints: " + "; ".join(item["expression"] for item in breakpoints) + "."
            if breakpoints
            else "No conditional audio breakpoints are set."
        )
        return jsonify({"success": True, "breakpoints": breakpoints, "speech": msg, "auto_speak": True})

    if action in {"clear", "delete", "remove"}:
        with _breakpoint_lock:
            _breakpoints.pop(session_id, None)
        msg = "Cleared all conditional audio breakpoints."
        return jsonify({"success": True, "breakpoints": [], "speech": msg, "auto_speak": True})

    condition_text = str(body.get("condition") or body.get("text") or body.get("command") or "").strip()
    if not condition_text and body.get("variable") and body.get("operator") and body.get("threshold") is not None:
        condition_text = f"{body.get('variable')} {body.get('operator')} {body.get('threshold')!r}"

    try:
        breakpoint = parse_conditional_breakpoint(condition_text)
    except ValueError as exc:
        msg = str(exc)
        return jsonify({"success": False, "error": msg, "speech": msg, "auto_speak": True}), 400

    if action in {"add", "set", "watch"}:
        with _breakpoint_lock:
            current = [
                item for item in _breakpoints.get(session_id, []) if item.get("expression") != breakpoint["expression"]
            ]
            current.append(breakpoint)
            _breakpoints[session_id] = current[-10:]

    breakpoints = _session_breakpoints(session_id)
    if not breakpoints or action in {"check", "run"}:
        breakpoints = [breakpoint]

    if not code.strip():
        msg = (
            f"Conditional audio breakpoint set: {breakpoint['expression']}."
            if action in {"add", "set", "watch"}
            else f"Ready to check: {breakpoint['expression']}."
        )
        return jsonify(
            {"success": True, "breakpoint": breakpoint, "breakpoints": breakpoints, "speech": msg, "auto_speak": True}
        )

    result = check_conditional_breakpoints(code, breakpoints, inputs=inputs)
    if result.get("triggered"):
        speech = result.get("speech") or "Conditional audio breakpoint hit."
    else:
        prefix = (
            f"Conditional audio breakpoint set: {breakpoint['expression']}. "
            if action in {"add", "set", "watch"}
            else ""
        )
        speech = prefix + (result.get("speech") or "No conditional audio breakpoint was hit.")
        result["speech"] = speech
    return jsonify({"breakpoint": breakpoint, "breakpoints": breakpoints, **result, "auto_speak": True})


@python_bp.route("/python/analyze", methods=["POST"])
def python_analyze_route():
    body = safejson()
    code = _body_code(body)
    result = analyze_python_code(code, mode=str(body.get("mode") or "analyze"), last_error=str(body.get("error") or ""))
    status = 200 if result.get("success") else 400
    return jsonify({**result, "auto_speak": True}), status


@python_bp.route("/python/audio-code-map", methods=["POST"])
def python_audio_code_map_route():
    body = safejson()
    code = _body_code(body)
    result = build_audio_code_map(code, query=str(body.get("query") or ""))
    status = 200 if result.get("success") else 400
    return jsonify({**result, "auto_speak": True}), status


@python_bp.route("/python/step-narration", methods=["POST"])
def python_step_narration_route():
    body = safejson()
    code = _body_code(body)
    ok, error = validate_python_code(code)
    if not ok:
        status = 413 if ("too large" in error.lower() or "too long" in error.lower()) else 400
        return jsonify({"success": False, "error": error, "speech": error, "auto_speak": True}), status
    result = build_step_narration(code, watched=_session_watches(get_session_id()), inputs=_body_inputs(body))
    if not result.get("success"):
        _record_run(get_session_id(), code, result)
    return jsonify({**result, "auto_speak": True})


@python_bp.route("/python/state-watch", methods=["POST"])
def python_state_watch_route():
    body = safejson()
    session_id = get_session_id()
    code = _body_code(body)
    inputs = _body_inputs(body)
    action = str(body.get("action") or "current").strip().lower()
    variable = str(body.get("variable") or "").strip()
    key = _state_key(code, inputs)

    if not code.strip():
        msg = "The Python editor is empty. Type or dictate Python code first."
        return jsonify({"success": False, "error": msg, "speech": msg, "auto_speak": True}), 400

    with _state_watch_lock:
        stored = dict(_state_watch.get(session_id, {}))

    if action in {"start", "reset", "run"} or stored.get("key") != key or not stored.get("steps"):
        model = build_state_watch_model(code, inputs=inputs)
        if not model.get("success") or not model.get("steps"):
            status = 200 if model.get("success") else 400
            return jsonify({**model, "auto_speak": True}), status
        stored = {
            "key": key,
            "code": code,
            "inputs": inputs or [],
            "steps": model.get("steps") or [],
            "cursor": 0,
            "output": model.get("output", ""),
            "trace": model.get("trace") or [],
        }

    steps = list(stored.get("steps") or [])
    cursor = int(stored.get("cursor") or 0)
    if body.get("cursor") is not None:
        try:
            cursor = int(body.get("cursor"))
        except (TypeError, ValueError):
            cursor = 0

    if action in {"next", "next_step"}:
        cursor = min(cursor + 1, max(len(steps) - 1, 0))
        explain_action = "current"
    elif action in {"previous", "previous_step", "back"}:
        cursor = max(cursor - 1, 0)
        explain_action = "current"
    elif action in {"first", "first_step"}:
        cursor = 0
        explain_action = "current"
    elif action in {"last", "last_step"}:
        cursor = max(len(steps) - 1, 0)
        explain_action = "current"
    elif action in {"repeat", "repeat_step"}:
        explain_action = "current"
    elif action in {"what_changed", "changed"}:
        explain_action = "what_changed"
    elif action in {"where", "where_am_i"}:
        explain_action = "where"
    elif action in {"why_variable_change", "why_variable_changed"}:
        explain_action = "why_variable_change"
    elif action in {"condition_pass", "condition_fail", "explain_condition", "condition"}:
        explain_action = "condition"
    elif action in {"loop", "explain_loop"}:
        explain_action = "loop"
    elif action in {"step_into", "enter_function", "function_into"}:
        current = steps[cursor] if steps else {}
        target = None
        call = current.get("function_call") if isinstance(current, dict) else None
        if call:
            function_name = call.get("function")
            target = next(
                (
                    index
                    for index, step in enumerate(steps[cursor + 1 :], start=cursor + 1)
                    if step.get("function_context") == function_name
                ),
                None,
            )
        if target is None:
            target = next(
                (
                    index
                    for index, step in enumerate(steps[cursor + 1 :], start=cursor + 1)
                    if step.get("function_call")
                ),
                None,
            )
        if target is not None:
            cursor = target
        explain_action = "step_into"
    elif action in {"step_out", "leave_function", "function_out"}:
        target = next(
            (index for index, step in enumerate(steps[cursor:], start=cursor) if step.get("function_return")),
            None,
        )
        if target is not None:
            cursor = target
        explain_action = "step_out"
    elif action in {"where_function", "current_function"}:
        explain_action = "current_function"
    elif action in {"function", "explain_function", "explain_function_call"}:
        explain_action = "function"
    elif action in {"arguments", "what_arguments"}:
        explain_action = "arguments"
    elif action in {"parameters", "what_parameters"}:
        explain_action = "parameters"
    elif action in {"return", "what_returned", "go_back", "where_back"}:
        explain_action = "return" if action in {"return", "what_returned"} else "go_back"
    elif action in {"why_function_return", "why_return"}:
        explain_action = "why_function_return"
    else:
        explain_action = "current"

    explanation = explain_state_watch_step(steps, cursor=cursor, action=explain_action, variable=variable)
    stored["cursor"] = cursor
    with _state_watch_lock:
        _state_watch[session_id] = stored

    return jsonify(
        {
            "success": explanation.get("success", True),
            "action": action,
            "cursor": cursor,
            "step": explanation.get("step"),
            "steps": steps,
            "total_steps": len(steps),
            "output": stored.get("output", ""),
            "explanation": explanation.get("explanation", ""),
            "speech": explanation.get("speech", ""),
            "auto_speak": True,
        }
    )


@python_bp.route("/python/watch-variable", methods=["POST"])
def python_watch_variable_route():
    body = safejson()
    session_id = get_session_id()
    action = str(body.get("action") or "check").strip().lower()
    variable = str(body.get("variable") or "").strip()
    code = _body_code(body)

    if action == "clear":
        with _watched_lock:
            _watched_vars.pop(session_id, None)
        msg = "Cleared all watched Python variables."
        return jsonify({"success": True, "watched": [], "speech": msg, "auto_speak": True})

    if action == "remove" and variable:
        with _watched_lock:
            watched = set(_watched_vars.get(session_id, set()))
            watched.discard(variable)
            _watched_vars[session_id] = watched
        msg = f"Stopped watching {variable}."
        return jsonify({"success": True, "watched": sorted(watched), "speech": msg, "auto_speak": True})

    if action in {"add", "watch"} or variable:
        if not variable:
            return jsonify({"success": False, "error": "No variable name provided."}), 400
        if not re.fullmatch(r"[A-Za-z_]\w*", variable):
            return jsonify({"success": False, "error": f"{variable!r} is not a valid Python variable name."}), 400
        with _watched_lock:
            watched = set(_watched_vars.get(session_id, set()))
            watched.add(variable)
            _watched_vars[session_id] = watched
        msg = f"Now watching {variable}."
        if code.strip():
            result = watch_variables(code, watched=watched, inputs=_body_inputs(body))
            return jsonify({"success": result["success"], "watched": sorted(watched), **result, "auto_speak": True})
        return jsonify({"success": True, "watched": sorted(watched), "speech": msg, "auto_speak": True})

    if not code.strip():
        watched = sorted(_session_watches(session_id))
        msg = (
            "Watched Python variables: " + ", ".join(watched) + "."
            if watched
            else "No Python variables are being watched."
        )
        return jsonify({"success": True, "watched": watched, "speech": msg, "auto_speak": True})

    watched = _session_watches(session_id)
    result = watch_variables(code, watched=watched or None, inputs=_body_inputs(body))
    return jsonify({"watched": sorted(watched), **result, "auto_speak": True})


@python_bp.route("/python/explain-error", methods=["POST"])
def python_explain_error_route():
    body = safejson()
    error = str(body.get("error") or "")
    code = _body_code(body)
    msg = explain_error(error, code)
    return jsonify({"success": True, "reply": msg, "speech": msg, "auto_speak": True})


@python_bp.route("/python/mistake-replay", methods=["POST"])
def python_mistake_replay_route():
    body = safejson()
    before = str(body.get("code_before") or body.get("before") or "")
    after = str(body.get("code_after") or body.get("after") or _body_code(body))
    if not before:
        with _mistake_lock:
            snap = dict(_mistakes.get(get_session_id(), {}))
        before = str(snap.get("error_code") or "")
        after = after or str(snap.get("success_code") or "")
    if not before or not after:
        msg = "I do not have a corrected Python mistake to replay yet. Run broken code, fix it, then run again."
        return jsonify({"success": False, "reply": msg, "speech": msg, "auto_speak": True})
    result = explain_mistake_replay(before, after)
    return jsonify({"success": True, **result, "code_before": before, "code_after": after, "auto_speak": True})
