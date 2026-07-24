from __future__ import annotations

import ast
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from codeup.config import DATA_DIR, env_int

MAX_PYTHON_CODE_SIZE = env_int("MAX_PYTHON_CODE_SIZE", 50_000, minimum=1000)
PYTHON_RUN_TIMEOUT = env_int("PYTHON_RUN_TIMEOUT", 5, minimum=1)
MAX_OUTPUT_CHARS = env_int("PYTHON_OUTPUT_LIMIT", 20_000, minimum=1000)
MAX_TRACE_EVENTS = env_int("PYTHON_TRACE_LIMIT", 5000, minimum=100)
MAX_INPUT_COUNT = env_int("PYTHON_INPUT_COUNT_LIMIT", 50, minimum=1)
MAX_INPUT_CHARS = env_int("PYTHON_INPUT_CHAR_LIMIT", 1000, minimum=1)
MAX_ERROR_CHARS = env_int("PYTHON_ERROR_LIMIT", 4000, minimum=500)
SPOKEN_OUTPUT_CHARS = 500

SOURCE_TOO_LONG_MSG = (
    f"Your Python code is too long for CodeUp Web to run safely. "
    f"Shorten it to {MAX_PYTHON_CODE_SIZE} characters or fewer, then try again."
)
TIMEOUT_MSG = (
    "Your program timed out because it ran for too long, so CodeUp stopped it. "
    "This often means a loop did not stop. Check the loop condition or add a break."
)
OUTPUT_TRUNCATED_MSG = "Your program produced too much output, so CodeUp shortened it."
TRACE_TRUNCATED_MSG = "Your program has too many steps to explain all at once."

_EXC_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Warning)):\s*(.*)$")
_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)(?:, in (\S+))?')
_INIT_RE = re.compile(r"^(\w+) initialized to (.+)$")
_CHANGE_RE = re.compile(r"^(\w+) changed from (.+) to (.+)$")
_SAFE_CONDITION_RE = re.compile(r"^[A-Za-z_]\w*\s*(?:==|!=|>=|<=|>|<)\s*(?:-?\d+(?:\.\d+)?|'.*?'|\".*?\"|True|False)$")


def validate_python_code(code: str) -> tuple[bool, str]:
    if len(code or "") > MAX_PYTHON_CODE_SIZE:
        return False, SOURCE_TOO_LONG_MSG
    if not (code or "").strip():
        return False, "Python code cannot be empty."
    if re.search(r"<\s*(html|script|style|body|div|button|section)\b", code or "", flags=re.I):
        return False, "This looks like web code. Use the website editor for HTML, CSS, and JavaScript."
    return True, ""


def validate_python_inputs(inputs: list[str] | None) -> tuple[bool, list[str], str]:
    if inputs is None:
        return True, [], ""
    if len(inputs) > MAX_INPUT_COUNT:
        return (
            False,
            [],
            f"Your program has too many queued inputs for CodeUp Web to handle safely. "
            f"Keep it to {MAX_INPUT_COUNT} inputs or fewer.",
        )
    cleaned: list[str] = []
    for index, item in enumerate(inputs, start=1):
        value = str(item).replace("\r", " ").replace("\n", " ")
        if len(value) > MAX_INPUT_CHARS:
            return (
                False,
                [],
                f"Input {index} is too long for CodeUp Web to handle safely. "
                f"Keep each input to {MAX_INPUT_CHARS} characters or fewer.",
            )
        cleaned.append(value)
    return True, cleaned, ""


def _runtime_root() -> Path:
    root = Path(DATA_DIR) / "python-runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _runner_path() -> Path:
    return Path(__file__).resolve().parents[1] / "runtime" / "python_runner.py"


def _bounded_pair(text: str, limit: int, marker: str) -> tuple[str, bool]:
    value = str(text or "")
    if len(value) <= limit:
        return value, False
    return value[:limit] + f"\n... {marker} ...", True


def _bounded(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    return _bounded_pair(text, limit, "output shortened")[0]


def _clip_error(text: str) -> tuple[str, bool]:
    return _bounded_pair(text, MAX_ERROR_CHARS, "error shortened")


def _output_speech(
    stdout: str, input_summary: str = "", output_truncated: bool = False, trace_truncated: bool = False
) -> str:
    if output_truncated:
        speech = OUTPUT_TRUNCATED_MSG + " The visible output panel shows the beginning of the output."
    elif not stdout:
        speech = "Program finished with no output."
    elif len(stdout.strip()) > SPOKEN_OUTPUT_CHARS or len(stdout.splitlines()) > 12:
        line_count = len(stdout.splitlines()) or 1
        speech = f"Program finished and printed {line_count} line(s). The full output is shown in the output panel."
    else:
        speech = f"Program output: {stdout.strip()}"
    if trace_truncated:
        speech += " " + TRACE_TRUNCATED_MSG
    if input_summary:
        speech += " " + input_summary
    return speech


def _read_trace_bundle(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _read_trace(path: Path) -> list[dict[str, Any]]:
    trace = _read_trace_bundle(path).get("trace")
    return trace if isinstance(trace, list) else []


def _input_summary(input_events: list[dict[str, Any]]) -> str:
    if not input_events:
        return ""
    parts = []
    for item in input_events[:20]:
        index = item.get("index") or len(parts) + 1
        prompt = str(item.get("prompt") or "").strip()
        label = f"Input {index}"
        if prompt:
            label += f" for prompt {prompt!r}"
        if item.get("provided") is False:
            parts.append(f"{label} was missing.")
        else:
            parts.append(f"{label} used {str(item.get('value') or '')!r}.")
    return " ".join(parts)


def _last_exception_line(raw_error: str) -> tuple[str, str]:
    lines = [line.strip() for line in str(raw_error or "").splitlines() if line.strip()]
    for line in reversed(lines):
        match = _EXC_RE.match(line)
        if match:
            return match.group(1), match.group(2).strip()
    return "", ""


def _student_line(raw_error: str) -> int | None:
    frames = _FRAME_RE.findall(str(raw_error or ""))
    for filename, line, _func in reversed(frames):
        if filename == "<user>" or filename.endswith("program.py"):
            try:
                return int(line)
            except ValueError:
                return None
    if frames:
        return None
    match = re.search(r"\bline\s+(\d+)\b", str(raw_error or ""), flags=re.I)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def user_facing_error(raw_error: str) -> str:
    exc_type, message = _last_exception_line(raw_error)
    line = _student_line(raw_error)
    if not exc_type:
        clean = re.sub(r"\s+", " ", str(raw_error or "")).strip()
        return clean[:500] or "The program stopped with an error."
    if line:
        return f"Line {line}: {exc_type}: {message}".strip()
    return f"{exc_type}: {message}".strip()


def _code_line(code: str, line: int | None) -> str:
    if not line:
        return ""
    rows = (code or "").splitlines()
    if 1 <= line <= len(rows):
        return rows[line - 1].strip()
    return ""


def explain_error(error_text: str, code: str = "") -> str:
    if not error_text:
        return "There is no Python error to explain."
    lower_text = str(error_text or "").lower()
    if "ran for too long" in lower_text or "timed out" in lower_text:
        return TIMEOUT_MSG + " What to check next: make sure a while loop can become false, or add a break."
    if "too much output" in lower_text or "output shortened" in lower_text:
        return OUTPUT_TRUNCATED_MSG + " What to check next: print fewer lines, or print a summary instead."
    if "too many steps" in lower_text or "trace limit" in lower_text:
        return TRACE_TRUNCATED_MSG + " What to check next: try a smaller loop when using Step Watch."
    exc_type, message = _last_exception_line(error_text)
    if not exc_type:
        match = re.match(
            r"(?:Line\s+(\d+):\s*)?([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Warning)):\s*(.*)", error_text
        )
        if match:
            exc_type, message = match.group(2), match.group(3)
    line = _student_line(error_text)
    if line is None:
        match = re.match(r"Line\s+(\d+):", error_text, flags=re.I)
        if match:
            line = int(match.group(1))

    where = f"line {line}" if line else "the failing line"
    lower = (message or error_text).lower()
    if exc_type in {"IndentationError", "TabError"}:
        cause = "Python expected indentation to show which lines belong inside a block."
        next_step = "Indent the line inside the loop, if statement, or function, usually by four spaces."
    elif exc_type == "SyntaxError":
        if "not available" in lower or "not allowed" in lower:
            cause = message or "That operation is not available in CodeUp Web Python mode."
            next_step = "Use the beginner-safe Python features available here, or ask CodeUp for a safe alternative."
        else:
            cause = f"Python could not understand the code structure near {where}."
            next_step = "Check for a missing colon, bracket, or quote on or just before that line."
    elif exc_type == "NameError":
        name_match = re.search(r"name '([^']+)'", message or "")
        name = name_match.group(1) if name_match else "that name"
        cause = f"The name {name} is used before Python has a value for it."
        next_step = f"Define {name} before this line, or check the spelling."
    elif exc_type == "TypeError":
        cause = "An operation was used with the wrong kind of value."
        next_step = "Check whether you need int(), str(), or float() to convert a value first."
    elif exc_type == "ValueError" and ("int" in lower or "float" in lower):
        cause = "Python tried to convert text into a number, but the text did not look numeric."
        next_step = "Use numeric input, or check the value before converting it."
    elif exc_type == "ZeroDivisionError":
        cause = "The code divided by zero."
        next_step = "Check the divisor before dividing."
    elif exc_type == "IndexError":
        cause = "The code asked for a list or string position that does not exist."
        next_step = "Check the length. Positions start at zero and end at length minus one."
    elif exc_type == "RuntimeError" and "asked for input number" in lower:
        cause = "The program reached an input() prompt, but the input queue did not have enough values."
        next_step = "Add one input value for each input() prompt, in the same order, then run with inputs."
    elif exc_type in {"ImportError", "SyntaxError"} and ("not available" in lower or "not allowed" in lower):
        cause = message or "That operation is not available in CodeUp Web Python mode."
        next_step = "Use beginner-safe Python here. File, network, subprocess, and introspection access are blocked."
    elif exc_type == "CodeUpOutputLimitError" or "too much output" in lower:
        cause = OUTPUT_TRUNCATED_MSG
        next_step = "Print fewer lines, or print a shorter summary."
    else:
        cause = "The program stopped while running this line."
        next_step = "Read the error type and check the named line."

    line_text = _code_line(code, line)
    parts = [f"The program crashed at {where}.", f"The error is {exc_type or 'an error'}.", cause]
    if line_text:
        parts.append(f"The line was: {line_text}")
    parts.append(f"What to check next: {next_step}")
    return " ".join(part for part in parts if part).strip()


def run_python_code(code: str, inputs: list[str] | None = None) -> dict[str, Any]:
    ok, error = validate_python_code(code)
    if not ok:
        return {"success": False, "output": "", "error": error, "trace": [], "speech": error}
    inputs_ok, safe_inputs, input_error = validate_python_inputs(inputs)
    if not inputs_ok:
        return {"success": False, "output": "", "error": input_error, "trace": [], "speech": input_error}

    root = _runtime_root()
    workdir = Path(tempfile.mkdtemp(prefix="run-", dir=str(root)))
    code_file = workdir / "program.py"
    trace_file = workdir / "trace.json"
    inputs_file = workdir / "inputs.txt"
    try:
        code_file.write_text(code, encoding="utf-8")
        if safe_inputs:
            inputs_file.write_text("\n".join(safe_inputs), encoding="utf-8")
        args = [
            sys.executable,
            str(_runner_path()),
            str(code_file),
            str(trace_file),
            str(inputs_file) if safe_inputs else "",
            str(MAX_OUTPUT_CHARS),
            str(MAX_TRACE_EVENTS),
        ]

        try:
            completed = subprocess.run(
                args,
                cwd=str(workdir),
                text=True,
                capture_output=True,
                timeout=PYTHON_RUN_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "", "error": TIMEOUT_MSG, "trace": [], "speech": TIMEOUT_MSG}

        trace_bundle = _read_trace_bundle(trace_file)
        trace = trace_bundle.get("trace") if isinstance(trace_bundle.get("trace"), list) else []
        input_events = trace_bundle.get("input_events") if isinstance(trace_bundle.get("input_events"), list) else []
        input_summary = _input_summary(input_events)
        stdout, parent_output_truncated = _bounded_pair(completed.stdout or "", MAX_OUTPUT_CHARS, "output shortened")
        stderr, error_truncated = _clip_error(completed.stderr or "")
        output_truncated = bool(trace_bundle.get("output_truncated")) or parent_output_truncated
        trace_truncated = bool(trace_bundle.get("trace_truncated")) or any(
            event.get("type") == "overflow" for event in trace if isinstance(event, dict)
        )
        limit_payload = {
            "output_truncated": output_truncated,
            "trace_truncated": trace_truncated,
            "error_truncated": error_truncated,
            "output_warning": OUTPUT_TRUNCATED_MSG if output_truncated else "",
            "trace_warning": TRACE_TRUNCATED_MSG if trace_truncated else "",
            "limits": {
                "runtime_seconds": PYTHON_RUN_TIMEOUT,
                "output_chars": MAX_OUTPUT_CHARS,
                "trace_events": MAX_TRACE_EVENTS,
                "input_count": MAX_INPUT_COUNT,
                "input_chars": MAX_INPUT_CHARS,
                "source_chars": MAX_PYTHON_CODE_SIZE,
                "error_chars": MAX_ERROR_CHARS,
            },
        }
        if completed.returncode == 3 or output_truncated:
            speech = _output_speech(stdout, input_summary, output_truncated=True, trace_truncated=trace_truncated)
            return {
                "success": True,
                "output": stdout,
                "error": "",
                "trace": trace,
                "input_events": input_events,
                "input_summary": input_summary,
                "inputs_consumed": trace_bundle.get("inputs_consumed", 0),
                "speech": speech,
                **limit_payload,
            }
        if completed.returncode != 0 or stderr.strip():
            friendly = user_facing_error(stderr) if stderr.strip() else "The program stopped with an error."
            explanation = explain_error(stderr or friendly, code)
            if error_truncated:
                explanation += " CodeUp shortened the internal error details before showing them."
            if trace_truncated:
                explanation += " " + TRACE_TRUNCATED_MSG
            if input_summary:
                explanation = f"{explanation} Inputs used: {input_summary}"
            return {
                "success": False,
                "output": stdout,
                "error": friendly,
                "trace": trace,
                "traceback": stderr,
                "explanation": explanation,
                "input_events": input_events,
                "input_summary": input_summary,
                "inputs_consumed": trace_bundle.get("inputs_consumed", 0),
                "speech": explanation,
                **limit_payload,
            }
        speech = _output_speech(stdout, input_summary, output_truncated=False, trace_truncated=trace_truncated)
        return {
            "success": True,
            "output": stdout,
            "error": "",
            "trace": trace,
            "input_events": input_events,
            "input_summary": input_summary,
            "inputs_consumed": trace_bundle.get("inputs_consumed", 0),
            "speech": speech,
            **limit_payload,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _line_range_for_node(node: ast.AST) -> tuple[int, int]:
    start = int(getattr(node, "lineno", 1) or 1)
    end = int(getattr(node, "end_lineno", start) or start)
    return start, end


def _assignment_names(node: ast.AST) -> list[str]:
    targets: list[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    elif isinstance(node, ast.AugAssign):
        targets = [node.target]
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
    return names


def _deepest_nesting(code: str) -> int:
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        best = 0
        for line in (code or "").splitlines():
            if line.strip():
                best = max(best, (len(line) - len(line.lstrip(" "))) // 4)
        return best

    block_types = (ast.For, ast.While, ast.If, ast.With, ast.Try, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    def walk(node: ast.AST, depth: int) -> int:
        best = depth
        for child in ast.iter_child_nodes(node):
            next_depth = depth + 1 if isinstance(child, block_types) else depth
            best = max(best, walk(child, next_depth))
        return best

    return walk(tree, 0)


def build_audio_code_map(code: str, query: str = "") -> dict[str, Any]:
    ok, error = validate_python_code(code) if (code or "").strip() else (True, "")
    if not ok:
        return {"success": False, "reply": error, "speech": error}
    lines = (code or "").splitlines()
    non_empty = [(index + 1, line) for index, line in enumerate(lines) if line.strip()]
    if not non_empty:
        msg = "Your Python editor is empty."
        return {"success": True, "reply": msg, "speech": msg, "map": {"line_count": 0}}

    query_lower = (query or "").lower()
    if "nest" in query_lower or "depth" in query_lower or "indent" in query_lower:
        depth = _deepest_nesting(code)
        msg = f"Your deepest Python nesting level is {depth}."
        return {"success": True, "reply": msg, "speech": msg, "map": {"nesting_depth": depth}}

    parts = [f"Your Python code has {len(lines)} lines, with {len(non_empty)} non-empty lines."]
    map_data: dict[str, Any] = {
        "line_count": len(lines),
        "non_empty": len(non_empty),
        "functions": [],
        "loops": [],
        "conditions": [],
        "assignments": [],
        "prints": [],
        "nesting_depth": _deepest_nesting(code),
        "syntax_error": "",
    }
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        msg = (
            f"Your Python code has a syntax problem near line {exc.lineno or '?'}. "
            "I can still describe the indentation map."
        )
        indent_bits = []
        for line_no, line in non_e…10213 tokens truncated…             "index": len(steps),
                "line": line,
                "source": source,
                "spoken_source": _friendly_source(source),
                "variables_before": dict(state),
                "variables_after": dict(state),
                "changed_variables": [],
                "output": "",
                "loop_context": _active_loop_context(loops, line, loop_counts, state),
                "function_context": function_name,
                "function_call_stack": stack_public,
                "function_locals": dict(active_calls[-1].get("local_variables") or {}) if active_calls else {},
                "function_call": None,
                "function_return": None,
                "function_event": "",
                "condition": None,
            }
            if per_print_mode and _is_print_line(code, line) and out_cursor < len(out_lines):
                step["output"] = out_lines[out_cursor][:200]
                out_cursor += 1
            steps.append(step)
            last_step_by_line[line] = step
            continue
        if event_type != "state_change":
            continue

        frame = event.get("frame")
        frame_key = frame if isinstance(frame, int) else 0
        causing = pending_cause_by_frame.get(frame_key)
        if causing is None:
            causing = event.get("line")
        step = last_step_by_line.get(causing) if isinstance(causing, int) else None
        changed = []
        for change in event.get("changes", []) or []:
            parsed = _parse_trace_change(change)
            if not parsed:
                continue
            name = parsed["variable"]
            old_display = parsed["old_display"]
            new_display = parsed["new_display"]
            if (
                new_display.startswith("<function ")
                and isinstance(causing, int)
                and _src_line(code, causing).lstrip().startswith("def ")
            ):
                continue
            state[name] = new_display
            changed.append({"name": name, "old": old_display, "new": new_display, "raw": change})
            if active_calls:
                active_calls[-1].setdefault("local_variables", {})[name] = new_display
        if step and changed:
            step["changed_variables"].extend(changed)
            step["variables_after"] = dict(state)
            if step.get("function_context") and active_calls:
                step["function_locals"] = dict(active_calls[-1].get("local_variables") or {})
                step["function_call_stack"] = [_function_public_info(item) for item in active_calls]
            loop = step.get("loop_context") or {}
            target = loop.get("target")
            if target and target in state:
                loop["target_value"] = state[target]
                step["loop_context"] = loop

    for step in steps:
        if not step.get("variables_after"):
            step["variables_after"] = dict(step.get("variables_before") or {})
    latest_state: dict[str, str] = {}
    for index, step in enumerate(steps):
        condition = conditions.get(step["line"])
        if condition:
            next_line = next((later["line"] for later in steps[index + 1 :] if later["line"] != step["line"]), None)
            result = _line_in_ranges(next_line, condition.get("body_ranges", []))
            condition_state = step.get("variables_before") or latest_state
            step["condition"] = {
                "expression": condition["expression"],
                "result": result,
                "reason": _condition_reason(condition, condition_state, result),
            }
        after = step.get("variables_after") or step.get("variables_before") or {}
        if after:
            latest_state = dict(after)
    total = len(steps)
    for index, step in enumerate(steps):
        return_info = step.get("function_return")
        if not return_info:
            continue
        function_name = return_info.get("function")
        next_step = next(
            (later for later in steps[index + 1 :] if later.get("function_context") != function_name),
            None,
        )
        if next_step:
            return_info["next_line"] = next_step.get("line")
            step["function_return"] = return_info
    for step in steps:
        step["total_steps"] = total
    return steps


def build_state_watch_model(code: str, inputs: list[str] | None = None) -> dict[str, Any]:
    ok, error = validate_python_code(code)
    if not ok:
        return {"success": False, "error": error, "speech": error, "steps": []}
    result = run_python_code(code, inputs=inputs)
    if not result.get("success"):
        speech = result.get("speech") or result.get("error") or "The program stopped with an error."
        return {**result, "steps": [], "speech": speech}
    steps = build_state_watch_steps(code, result.get("trace") or [], result.get("output") or "")
    if not steps:
        msg = "I did not capture navigable Python steps. Try a small program with assignments, loops, or print statements."
        return {**result, "success": True, "steps": [], "speech": msg}
    return {**result, "steps": steps, "step_count": len(steps)}


def _nearest_condition_step(steps: list[dict[str, Any]], cursor: int) -> dict[str, Any] | None:
    if not steps:
        return None
    cursor = max(0, min(cursor, len(steps) - 1))
    candidates = [step for step in steps if step.get("condition") and step.get("condition", {}).get("expression")]
    if not candidates:
        return None
    return min(candidates, key=lambda step: abs(int(step["index"]) - cursor))


def explain_state_watch_step(
    steps: list[dict[str, Any]],
    cursor: int = 0,
    action: str = "current",
    variable: str = "",
) -> dict[str, Any]:
    if not steps:
        msg = "There are no navigable Python steps yet. Run Step Watch after writing code."
        return {"success": False, "speech": msg, "explanation": msg, "step": None, "cursor": 0, "total_steps": 0}

    cursor = max(0, min(int(cursor or 0), len(steps) - 1))
    step = steps[cursor]
    action = (action or "current").strip().lower()
    parts: list[str] = []

    if action in {"what_changed", "changed"}:
        if step.get("changed_variables"):
            parts.extend(_changed_variable_sentence(change) for change in step["changed_variables"])
        else:
            parts.append("No variable changed on this step.")
    elif action in {"where", "where_am_i"}:
        parts.append(
            f"You are on step {cursor + 1} of {len(steps)}, line {step['line']}: {step.get('spoken_source') or step.get('source')}."
        )
        loop_sentence = _step_loop_sentence(step)
        if loop_sentence:
            parts.append(loop_sentence)
        if step.get("function_context"):
            parts.append(f"You are inside function {step['function_context']}.")
    elif action in {"why_variable_change", "why_variable_changed"}:
        changes = step.get("changed_variables") or []
        chosen = next((change for change in changes if change.get("name") == variable), None) if variable else None
        chosen = chosen or (changes[0] if changes else None)
        if chosen:
            parts.append(_changed_variable_sentence(chosen))
            parts.append(
                f"That happened because Python ran line {step['line']}: {step.get('spoken_source') or step.get('source')}."
            )
        else:
            name = variable or "that variable"
            parts.append(f"{name} did not change on this step.")
    elif action in {"current_function", "where_function"}:
        function_step = step if step.get("function_context") else _nearest_function_step(steps, cursor, "context")
        if function_step and function_step.get("function_context"):
            parts.append(_call_stack_sentence(function_step))
            parts.append(_local_variables_sentence(function_step.get("function_locals") or {}))
        elif function_step and function_step.get("function_call"):
            parts.append(_function_call_sentence(function_step["function_call"]))
        else:
            parts.append("You are not inside a function on this step.")
    elif action in {"function", "explain_function", "function_call", "step_into"}:
        function_step = (
            step
            if (step.get("function_call") or step.get("function_context"))
            else _nearest_function_step(steps, cursor)
        )
        if function_step and function_step.get("function_call"):
            parts.append(_function_call_sentence(function_step["function_call"]))
        elif function_step and function_step.get("function_context"):
            parts.append(_call_stack_sentence(function_step))
            parts.append(_local_variables_sentence(function_step.get("function_locals") or {}))
        elif function_step and function_step.get("function_return"):
            parts.append(_function_return_sentence(function_step["function_return"]))
        else:
            parts.append("I do not see a function call in the captured steps.")
    elif action in {"arguments", "what_arguments"}:
        function_step = step if step.get("function_call") else _nearest_function_step(steps, cursor, "call")
        call = (function_step or {}).get("function_call") if function_step else None
        if call:
            params = call.get("parameters") or []
            if params:
                parts.append(f"The call to {call.get('function')} passed {_format_name_values(params)}.")
            elif call.get("arguments"):
                parts.append(f"The call to {call.get('function')} passed {', '.join(call['arguments'])}.")
            else:
                parts.append(f"The call to {call.get('function')} did not pass any arguments.")
        else:
            parts.append("I do not see function arguments in the captured steps.")
    elif action in {"parameters", "what_parameters"}:
        function_step = (
            step
            if (step.get("function_call") or step.get("function_context"))
            else _nearest_function_step(steps, cursor, "context")
        )
        call = (function_step or {}).get("function_call") if function_step else None
        if not call and function_step:
            stack = function_step.get("function_call_stack") or []
            call = stack[-1] if stack else None
        if call:
            names = [item.get("name") for item in call.get("parameters") or [] if item.get("name")]
            if names:
                parts.append(f"{call.get('function')} has parameters {', '.join(names)}.")
                values = _format_name_values(call.get("parameters") or [])
                if values:
                    parts.append(f"In this call, {values}.")
            else:
                parts.append(f"{call.get('function')} has no parameters.")
        else:
            parts.append("I do not see parameter information for this step.")
    elif action in {"return", "what_returned", "step_out", "go_back"}:
        function_step = step if step.get("function_return") else _nearest_function_step(steps, cursor, "return")
        return_info = (function_step or {}).get("function_return") if function_step else None
        if return_info:
            parts.append(_function_return_sentence(return_info))
        else:
            parts.append("I do not see a function return in the captured steps.")
    elif action in {"why_function_return", "why_return"}:
        function_step = step if step.get("function_return") else _nearest_function_step(steps, cursor, "return")
        return_info = (function_step or {}).get("function_return") if function_step else None
        if return_info:
            line_text = function_step.get("spoken_source") or function_step.get("source") or "the return line"
            value = return_info.get("return_value")
            locals_text = _local_variables_sentence(
                return_info.get("local_variables") or {}, return_info.get("parameters") or []
            )
            parts.append(
                f"The function {return_info.get('function')} returned {value} because Python ran line {function_step['line']}: {line_text}."
            )
            if locals_text:
                parts.append(locals_text)
        else:
            parts.append("I do not see a function return to explain.")
    elif action in {"condition", "condition_pass", "condition_fail", "explain_condition"}:
        condition_step = step if step.get("condition") else _nearest_condition_step(steps, cursor)
        condition = (condition_step or {}).get("condition") if condition_step else None
        if condition:
            parts.append(condition.get("reason") or "I found the condition, but could not explain its values.")
        else:
            parts.append("I did not see a condition result in the captured steps.")
    elif action in {"loop", "explain_loop"}:
        loop_sentence = _step_loop_sentence(step)
        parts.append(loop_sentence or "I do not see an active loop on this step.")
    else:
        parts.append(
            f"Step {cursor + 1} of {len(steps)}. You are on line {step['line']}: {step.get('spoken_source') or step.get('source')}."
        )
        if step.get("function_call"):
            parts.append(_function_call_sentence(step["function_call"]))
        if step.get("changed_variables"):
            parts.extend(_changed_variable_sentence(change) for change in step["changed_variables"][:3])
        if step.get("output"):
            parts.append(f"The program prints {step['output']}.")
        if step.get("function_return"):
            parts.append(_function_return_sentence(step["function_return"]))
        loop_sentence = _step_loop_sentence(step)
        if loop_sentence:
            parts.append(loop_sentence)
        if step.get("condition"):
            parts.append(step["condition"].get("reason", ""))
        if step.get("function_context") and not step.get("function_return"):
            stack_sentence = _call_stack_sentence(step)
            if stack_sentence:
                parts.append(stack_sentence)

    explanation = " ".join(part for part in parts if part).strip()
    return {
        "success": True,
        "speech": explanation,
        "explanation": explanation,
        "step": step,
        "cursor": cursor,
        "total_steps": len(steps),
    }


def _summarize_value(value: str) -> str:
    text = str(value or "")
    if text.startswith("["):
        inner = text[1:-1].strip()
        count = 0 if not inner else inner.count(",") + 1
        return f"a list with {count} item(s)"
    if text.startswith("{") and ":" in text:
        return "a dictionary"
    if len(text) > 80:
        return "a large value"
    return text


def narrate_state(state: dict[str, dict[str, Any]], output: str = "") -> str:
    if not state:
        base = "I did not capture any variable values from the last run."
    else:
        lines = ["Current Python state:"]
        for name, info in list(state.items())[:12]:
            line = f" on line {info['line']}" if info.get("line") else ""
            lines.append(f"{name} is {_summarize_value(info['value'])}{line}.")
        base = " ".join(lines)
    if output:
        count = len(output.splitlines())
        base += f" The program printed {count} line{'s' if count != 1 else ''}."
    return base


def watch_variables(code: str, watched: set[str] | None = None, inputs: list[str] | None = None) -> dict[str, Any]:
    watched = watched or set()
    result = run_python_code(code, inputs=inputs)
    if not result.get("success"):
        speech = result.get("speech") or result.get("error") or "The program stopped with an error."
        return {
            "success": False,
            "state": {},
            "speech": speech,
            "error": result.get("error", ""),
            "output": result.get("output", ""),
        }
    state = parse_state(result.get("trace") or [], watched=watched or None)
    speech = narrate_state(state, result.get("output", ""))
    return {"success": True, "state": state, "speech": speech, "output": result.get("output", "")}


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def code_diff(before: str, after: str) -> dict[str, Any]:
    before_lines = (before or "").splitlines()
    after_lines = (after or "").splitlines()
    changes = []
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for index in range(min(i2 - i1, j2 - j1)):
                before_line = before_lines[i1 + index]
                after_line = after_lines[j1 + index]
                changes.append(
                    {
                        "line": j1 + index + 1,
                        "kind": "changed",
                        "before": before_line,
                        "after": after_line,
                        "before_indent": _indent_width(before_line),
                        "after_indent": _indent_width(after_line),
                    }
                )
        elif tag == "delete":
            for index in range(i1, i2):
                changes.append({"line": index + 1, "kind": "removed", "before": before_lines[index], "after": ""})
        elif tag == "insert":
            for index in range(j1, j2):
                changes.append({"line": index + 1, "kind": "added", "before": "", "after": after_lines[index]})
    structural = []
    for change in changes:
        if change.get("kind") == "changed" and change.get("before_indent") != change.get("after_indent"):
            direction = "indented" if change["after_indent"] > change["before_indent"] else "unindented"
            movement = "into" if change["after_indent"] > change["before_indent"] else "out of"
            structural.append(
                f"Line {change['line']} was {direction} from {change['before_indent']} to {change['after_indent']} spaces, so it moved {movement} the surrounding block."
            )
    return {"changes": changes[:20], "total_changes": len(changes), "structural_changes": structural}


def explain_mistake_replay(before: str, after: str) -> dict[str, Any]:
    diff = code_diff(before, after)
    if not diff["changes"]:
        reply = "I see no differences between the two Python versions."
        return {"reply": reply, "speech": reply, "diff": diff}
    parts = [f"There are {diff['total_changes']} changed line(s)."]
    parts.extend(diff.get("structural_changes", [])[:3])
    for change in diff["changes"][:5]:
        if change["kind"] == "changed":
            if change["before"].strip() == change["after"].strip() and change.get("before_indent") != change.get(
                "after_indent"
            ):
                parts.append(
                    f"Line {change['line']} kept {change['after'].strip()} but changed indentation from {change.get('before_indent', 0)} to {change.get('after_indent', 0)} spaces."
                )
            else:
                parts.append(
                    f"Line {change['line']} changed from {change['before'].strip()} to {change['after'].strip()}."
                )
        elif change["kind"] == "added":
            parts.append(f"Line {change['line']} was added: {change['after'].strip()}.")
        elif change["kind"] == "removed":
            parts.append(f"A line was removed: {change['before'].strip()}.")
    reply = " ".join(parts)
    return {"reply": reply, "speech": reply, "diff": diff}
