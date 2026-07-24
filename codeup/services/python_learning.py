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


def _src_line(code: str, line_no: int | None) -> str:
    lines = (code or "").splitlines()
    return lines[line_no - 1].strip() if line_no and 1 <= line_no <= len(lines) else ""


def _friendly_source(source: str) -> str:
    text = (source or "").strip()
    return "print " + text[6:-1] if text.startswith("print(") and text.endswith(")") else text


def _literal_source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "value"


def _node_source(code: str, node: ast.AST) -> str:
    return _src_line(code, getattr(node, "lineno", None))


def analyze_python_code(code: str, mode: str = "analyze", last_error: str = "") -> dict[str, Any]:
    ok, error = validate_python_code(code)
    if not ok:
        return {"success": False, "error": error, "analysis": error, "speech": error}
    if not code.strip():
        msg = "The Python editor is empty. Add Python code first."
        return {"success": False, "error": msg, "analysis": msg, "speech": msg}
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        msg = explain_error(f"SyntaxError: {exc.msg}", code)
        return {"success": False, "error": msg, "analysis": msg, "speech": msg}
    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    loops = [node for node in ast.walk(tree) if isinstance(node, (ast.For, ast.While))]
    conditions = [node for node in ast.walk(tree) if isinstance(node, ast.If)]
    assignments = []
    prints = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            assignments.extend(_assignment_names(node))
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
            prints.append(node)
    parts = [f"Your Python code has {len((code or '').splitlines())} lines."]
    parts.append(f"It uses {len(loops)} loops, {len(conditions)} conditions, and {len(set(assignments))} variables.")
    if functions:
        parts.append("Functions: " + ", ".join(functions) + ".")
    if assignments:
        parts.append("Variables include " + ", ".join(sorted(set(assignments))[:8]) + ".")
    if prints:
        parts.append(f"It prints output on {len(prints)} line(s).")
    if last_error:
        parts.append(explain_error(last_error, code))
    analysis = " ".join(parts)
    return {"success": True, "analysis": analysis, "speech": analysis, "mode": mode}


def build_audio_code_map(code: str, query: str = "") -> dict[str, Any]:
    ok, error = validate_python_code(code) if (code or "").strip() else (True, "")
    if not ok:
        return {"success": False, "reply": error, "speech": error}
    lines = (code or "").splitlines()
    non_empty = [(index + 1, line) for index, line in enumerate(lines) if line.strip()]
    if not non_empty:
        msg = "Your Python editor is empty."
        return {"success": True, "reply": msg, "speech": msg, "map": {"line_count": 0}}
    if any(word in (query or "").lower() for word in ("nest", "depth", "indent")):
        depth = _deepest_nesting(code)
        msg = f"Your deepest Python nesting level is {depth}."
        return {"success": True, "reply": msg, "speech": msg, "map": {"nesting_depth": depth}}
    map_data = {
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
        bits = [f"line {line_no} has {_indent_width(line)} leading spaces" for line_no, line in non_empty[:8]]
        msg = f"Your Python code has a syntax problem near line {exc.lineno or '?'}. " + "; ".join(bits) + "."
        return {"success": True, "reply": msg, "speech": msg, "map": {**map_data, "syntax_error": exc.msg}}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            map_data["functions"].append(
                {"name": node.name, "line": node.lineno, "parameters": [arg.arg for arg in node.args.args]}
            )
        elif isinstance(node, ast.For):
            map_data["loops"].append({"kind": "for loop", "line": node.lineno, "source": _node_source(code, node)})
        elif isinstance(node, ast.While):
            map_data["loops"].append({"kind": "while loop", "line": node.lineno, "source": _node_source(code, node)})
        elif isinstance(node, ast.If):
            map_data["conditions"].append({"line": node.lineno, "expression": _literal_source(node.test)})
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for name in _assignment_names(node):
                map_data["assignments"].append({"name": name, "line": getattr(node, "lineno", 0)})
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
            map_data["prints"].append({"line": getattr(node, "lineno", 0), "source": _node_source(code, node)})
    parts = [f"Your Python code has {len(lines)} lines, with {len(non_empty)} non-empty lines."]
    if map_data["loops"]:
        parts.append(
            "It has " + ", ".join(f"a {item['kind']} on line {item['line']}" for item in map_data["loops"][:4]) + "."
        )
    if map_data["assignments"]:
        parts.append(
            "Variables include " + ", ".join(sorted({item["name"] for item in map_data["assignments"]})[:8]) + "."
        )
    if map_data["functions"]:
        parts.append("Functions include " + ", ".join(item["name"] for item in map_data["functions"][:5]) + ".")
    if map_data["prints"]:
        parts.append(f"It prints on {len(map_data['prints'])} line(s).")
    reply = " ".join(parts)
    return {"success": True, "reply": reply, "speech": reply, "map": map_data}


def build_step_narration(code: str, watched: set[str] | None = None, inputs: list[str] | None = None) -> dict[str, Any]:
    result = run_python_code(code, inputs=inputs)
    if not result.get("success"):
        return result
    output_lines = (result.get("output") or "").splitlines()
    out_cursor = 0
    narration, indent_depths = [], []
    source_lines = (code or "").splitlines()
    for event in result.get("trace") or []:
        if event.get("type") != "line_exec":
            continue
        line_no = int(event.get("line") or 0)
        source = _src_line(code, line_no)
        if not source:
            continue
        if _is_print_line(code, line_no) and out_cursor < len(output_lines):
            narration.append(f"The program prints {output_lines[out_cursor]}.")
            out_cursor += 1
        elif source.startswith(("for ", "while ")):
            narration.append(f"Line {line_no} starts a loop: {source}.")
        elif source.startswith("if "):
            narration.append(f"Line {line_no} checks a condition: {source}.")
        elif "=" in source:
            narration.append(f"Line {line_no} updates a value: {source}.")
        else:
            narration.append(f"Line {line_no} runs: {_friendly_source(source)}.")
        indent_depths.append(
            (_indent_width(source_lines[line_no - 1]) // 4) if line_no and line_no <= len(source_lines) else 0
        )
    return {
        **result,
        "success": True,
        "narration": narration,
        "indent_depths": indent_depths,
        "speech": f"I narrated {len(narration)} Python step(s).",
    }


def parse_conditional_breakpoint(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Tell me a condition, like total > 10.")
    lowered = raw.lower().strip()
    for prefix in ("conditional breakpoint", "breakpoint", "break when", "stop when", "pause when", "when"):
        if lowered.startswith(prefix):
            raw = raw[len(prefix) :].strip()
            lowered = raw.lower().strip()
            break
    expression = f" {raw} "
    lower_expr = expression.lower()
    replacements = [
        (" is greater than or equal to ", " >= "),
        (" greater than or equal to ", " >= "),
        (" is less than or equal to ", " <= "),
        (" less than or equal to ", " <= "),
        (" is greater than ", " > "),
        (" greater than ", " > "),
        (" is less than ", " < "),
        (" less than ", " < "),
        (" is not equal to ", " != "),
        (" not equal to ", " != "),
        (" equals ", " == "),
        (" is ", " == "),
    ]
    for before, after in replacements:
        if before in lower_expr:
            start = lower_expr.index(before)
            expression = expression[:start] + after + expression[start + len(before) :]
            break
    expression = expression.strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("That breakpoint condition needs a simple comparison, like total > 10.") from exc
    if not _condition_ast_is_safe(tree.body):
        raise ValueError("Conditional audio breakpoints only support simple variable comparisons.")
    return {"expression": ast.unparse(tree.body), "source": raw}


def _condition_ast_is_safe(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    if not isinstance(node.left, ast.Name) or node.left.id.startswith("_"):
        return False
    if not isinstance(node.ops[0], (ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE)):
        return False
    return isinstance(node.comparators[0], ast.Constant) and isinstance(
        node.comparators[0].value, (int, float, str, bool)
    )


def _coerce_trace_value(value: str) -> Any:
    try:
        return ast.literal_eval(str(value))
    except Exception:
        text = str(value)
        if text in {"True", "False"}:
            return text == "True"
        for caster in (int, float):
            try:
                return caster(text)
            except ValueError:
                pass
        return text


def _eval_condition_expression(expression: str, state: dict[str, str]) -> bool:
    tree = ast.parse(expression, mode="eval")
    if not _condition_ast_is_safe(tree.body):
        return False
    compare = tree.body
    assert isinstance(compare, ast.Compare)
    left = _coerce_trace_value(state.get(compare.left.id, ""))
    right = compare.comparators[0].value
    try:
        if isinstance(compare.ops[0], ast.Eq):
            return left == right
        if isinstance(compare.ops[0], ast.NotEq):
            return left != right
        if isinstance(compare.ops[0], ast.Gt):
            return left > right
        if isinstance(compare.ops[0], ast.GtE):
            return left >= right
        if isinstance(compare.ops[0], ast.Lt):
            return left < right
        if isinstance(compare.ops[0], ast.LtE):
            return left <= right
    except TypeError:
        return False
    return False


def _parse_trace_change(change: str) -> dict[str, str] | None:
    text = str(change or "")
    match = _INIT_RE.match(text)
    if match:
        return {"variable": match.group(1), "old_display": "", "new_display": match.group(2)}
    match = _CHANGE_RE.match(text)
    if match:
        return {"variable": match.group(1), "old_display": match.group(2), "new_display": match.group(3)}
    if text.endswith(" went out of scope"):
        return {"variable": text[: -len(" went out of scope")], "old_display": "", "new_display": "out of scope"}
    return None


def parse_state(trace: list[dict[str, Any]], watched: set[str] | None = None) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    watched = watched or set()
    for event in trace or []:
        if event.get("type") != "state_change":
            continue
        line = int(event.get("line") or 0)
        for change in event.get("changes") or []:
            parsed = _parse_trace_change(change)
            if not parsed:
                continue
            name = parsed["variable"]
            if watched and name not in watched:
                continue
            if parsed["new_display"] == "out of scope":
                state.pop(name, None)
            else:
                state[name] = {"value": parsed["new_display"], "line": line, "change": change}
    return state


def evaluate_conditional_breakpoints(
    trace: list[dict[str, Any]], breakpoints: list[dict[str, Any]], code: str = ""
) -> dict[str, Any]:
    state: dict[str, str] = {}
    pending_line_by_frame: dict[int, int] = {}
    cause_line_by_frame: dict[int, int] = {}
    for event in trace or []:
        event_type = event.get("type")
        frame = event.get("frame") if isinstance(event.get("frame"), int) else 0
        if event_type == "line_exec":
            line_no = int(event.get("line") or 0)
            cause_line_by_frame[frame] = pending_line_by_frame.get(frame, line_no)
            pending_line_by_frame[frame] = line_no
            continue
        if event_type != "state_change":
            continue
        causing_line = cause_line_by_frame.get(frame, int(event.get("line") or 0))
        for change in event.get("changes") or []:
            parsed = _parse_trace_change(change)
            if parsed and parsed["new_display"] != "out of scope":
                state[parsed["variable"]] = parsed["new_display"]
        for breakpoint in breakpoints or []:
            expression = str(breakpoint.get("expression") or "")
            if expression and _eval_condition_expression(expression, state):
                context = ", ".join(f"{name} is {value}" for name, value in sorted(state.items())[:6])
                speech = f"Conditional audio breakpoint hit on line {causing_line}: {expression}. {context}."
                return {
                    "success": True,
                    "triggered": True,
                    "line": causing_line,
                    "condition": breakpoint,
                    "context": context,
                    "speech": speech,
                    "source": _src_line(code, causing_line),
                }
    return {"success": True, "triggered": False, "speech": "No conditional audio breakpoint was hit."}


def check_conditional_breakpoints(
    code: str, breakpoints: list[dict[str, Any]], inputs: list[str] | None = None
) -> dict[str, Any]:
    result = run_python_code(code, inputs=inputs)
    if not result.get("success"):
        return result
    return {**result, **evaluate_conditional_breakpoints(result.get("trace") or [], breakpoints, code=code)}


def _function_definitions(code: str) -> dict[str, dict[str, Any]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            out[node.name] = {
                "function": node.name,
                "definition_line": node.lineno,
                "parameters": [arg.arg for arg in node.args.args],
                "end_line": getattr(node, "end_lineno", node.lineno),
            }
    return out


def _call_arguments_by_line(code: str, definitions: dict[str, dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    calls: dict[int, list[dict[str, Any]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        if name in definitions:
            calls.setdefault(getattr(node, "lineno", 0), []).append(
                {"function": name, "arguments": [_literal_source(arg) for arg in node.args]}
            )
    return calls


def _line_in_ranges(line_no: int | None, ranges: list[tuple[int, int]]) -> bool:
    return bool(line_no) and any(start <= int(line_no) <= end for start, end in ranges)


def _loop_infos(code: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    loops = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.While)):
            continue
        body_ranges = [
            (child.lineno, getattr(child, "end_lineno", child.lineno))
            for child in node.body
            if hasattr(child, "lineno")
        ]
        target = _literal_source(node.target) if isinstance(node, ast.For) else ""
        loops.append(
            {
                "line": node.lineno,
                "kind": "for" if isinstance(node, ast.For) else "while",
                "target": target if re.fullmatch(r"[A-Za-z_]\w*", target or "") else "",
                "body_start": node.body[0].lineno if node.body else node.lineno,
                "body_ranges": body_ranges,
                "source": _src_line(code, node.lineno),
            }
        )
    return sorted(loops, key=lambda item: item["line"])


def _condition_infos(code: str) -> dict[int, dict[str, Any]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            out[node.lineno] = {
                "line": node.lineno,
                "expression": _literal_source(node.test),
                "body_ranges": [(child.lineno, getattr(child, "end_lineno", child.lineno)) for child in node.body],
            }
    return out


def _active_loop_context(
    loops: list[dict[str, Any]], line_no: int, counts: dict[tuple[int, int], int], state: dict[str, str], frame: int = 0
) -> dict[str, Any] | None:
    active = [loop for loop in loops if _line_in_ranges(line_no, loop.get("body_ranges", []))]
    if not active:
        return None
    loop = active[-1]
    key = (loop["line"], frame)
    if line_no == loop.get("body_start"):
        counts[key] = counts.get(key, 0) + 1
    context = {
        "line": loop["line"],
        "kind": loop["kind"],
        "source": loop["source"],
        "iteration": counts.get(key, 1),
        "target": loop.get("target", ""),
    }
    if context["target"] and context["target"] in state:
        context["target_value"] = state[context["target"]]
    return context


def _is_print_line(code: str, line_no: int) -> bool:
    return _src_line(code, line_no).lstrip().startswith("print(")


def _condition_reason(condition: dict[str, Any], state: dict[str, str], result: bool) -> str:
    expression = condition.get("expression") or "condition"
    truth = "true" if result else "false"
    variable = ""
    try:
        tree = ast.parse(str(expression), mode="eval")
        if isinstance(tree.body, ast.Compare) and isinstance(tree.body.left, ast.Name):
            variable = tree.body.left.id
    except Exception:
        pass
    value_text = f" because {variable} is currently {state.get(variable)}" if variable and variable in state else ""
    return f"{expression} is {truth}{value_text}."


def _function_public_info(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "function": item.get("function"),
        "definition_line": item.get("definition_line"),
        "call_line": item.get("call_line"),
        "caller": item.get("caller", ""),
        "parameters": list(item.get("parameters") or []),
    }


def build_state_watch_steps(code: str, trace: list[dict[str, Any]], output: str = "") -> list[dict[str, Any]]:
    definitions = _function_definitions(code)
    calls_by_line = _call_arguments_by_line(code, definitions)
    loops = _loop_infos(code)
    conditions = _condition_infos(code)
    out_lines = [line for line in (output or "").splitlines() if line.strip()]
    out_cursor = 0
    steps: list[dict[str, Any]] = []
    state: dict[str, str] = {}
    pending: dict[int, int] = {}
    cause_by_frame: dict[int, int] = {}
    last_by_line: dict[int, dict[str, Any]] = {}
    last_by_line_frame: dict[tuple[int, int], dict[str, Any]] = {}
    loop_counts: dict[tuple[int, int], int] = {}
    active_calls: list[dict[str, Any]] = []
    for event in trace or []:
        event_type = event.get("type")
        frame = event.get("frame") if isinstance(event.get("frame"), int) else 0
        if event_type == "call":
            function = str(event.get("function") or "")
            if function == "<module>":
                continue
            definition = definitions.get(function, {})
            caller_line = event.get("caller_line") if isinstance(event.get("caller_line"), int) else None
            call_source = (calls_by_line.get(caller_line or 0) or [{"function": function, "arguments": []}])[0]
            locals_now = dict(event.get("locals") or {})
            params = []
            args = call_source.get("arguments") or []
            for index, name in enumerate(definition.get("parameters") or []):
                params.append(
                    {
                        "name": name,
                        "value": locals_now.get(name, ""),
                        "argument": args[index] if index < len(args) else "",
                    }
                )
            info = {
                "function": function,
                "definition_line": definition.get("definition_line", event.get("line")),
                "call_line": caller_line,
                "caller": active_calls[-1]["function"] if active_calls else "",
                "parameters": params,
                "arguments": args,
                "local_variables": locals_now,
                "frame": frame,
            }
            if caller_line and caller_line in last_by_line:
                last_by_line[caller_line]["function_call"] = _function_public_info(info)
            active_calls.append(info)
            continue
        if event_type == "return":
            function = str(event.get("function") or "")
            if function == "<module>":
                continue
            line_no = int(event.get("line") or 0)
            step = last_by_line_frame.get((line_no, frame)) or last_by_line.get(line_no)
            call_info = next((item for item in reversed(active_calls) if item.get("frame") == frame), None)
            if step:
                step["function_return"] = {
                    "function": function,
                    "return_value": str(event.get("value", "")),
                    "line": line_no,
                    "call_line": (call_info or {}).get("call_line") or event.get("caller_line"),
                    "caller_line": event.get("caller_line"),
                    "local_variables": dict(event.get("locals") or {}),
                    "parameters": (call_info or {}).get("parameters") or [],
                }
                step["function_event"] = "return"
            active_calls = [item for item in active_calls if item.get("frame") != frame]
            continue
        if event_type == "line_exec":
            line_no = int(event.get("line") or 0)
            source = _src_line(code, line_no)
            if not source:
                continue
            cause_by_frame[frame] = pending.get(frame, line_no)
            pending[frame] = line_no
            function = str(event.get("function") or "")
            function = "" if function == "<module>" else function
            step = {
                "index": len(steps),
                "line": line_no,
                "source": source,
                "spoken_source": _friendly_source(source),
                "variables_before": dict(state),
                "variables_after": dict(state),
                "changed_variables": [],
                "output": "",
                "loop_context": _active_loop_context(loops, line_no, loop_counts, state, frame),
                "function_context": function,
                "function_call_stack": [_function_public_info(item) for item in active_calls],
                "function_locals": dict(active_calls[-1].get("local_variables") or {}) if active_calls else {},
                "function_call": None,
                "function_return": None,
                "function_event": "",
                "condition": None,
            }
            if _is_print_line(code, line_no) and out_cursor < len(out_lines):
                step["output"] = out_lines[out_cursor][:200]
                out_cursor += 1
            steps.append(step)
            last_by_line[line_no] = step
            last_by_line_frame[(line_no, frame)] = step
            continue
        if event_type != "state_change":
            continue
        causing = cause_by_frame.get(frame, event.get("line"))
        step = last_by_line_frame.get((causing, frame)) if isinstance(causing, int) else None
        changed = []
        for change in event.get("changes") or []:
            parsed = _parse_trace_change(change)
            if not parsed:
                continue
            name, old, new = parsed["variable"], parsed["old_display"], parsed["new_display"]
            if (
                new.startswith("<function ")
                and isinstance(causing, int)
                and _src_line(code, causing).startswith("def ")
            ):
                continue
            if new == "out of scope":
                state.pop(name, None)
            else:
                state[name] = new
            changed.append({"name": name, "old": old, "new": new, "raw": change})
            if active_calls:
                active_calls[-1].setdefault("local_variables", {})[name] = new
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
        current_line = event.get("line") if isinstance(event.get("line"), int) else None
        current_step = last_by_line_frame.get((current_line, frame)) if current_line else None
        if current_step and current_step is not step:
            loop = current_step.get("loop_context") or {}
            target = loop.get("target")
            if target and target in state:
                loop["target_value"] = state[target]
                current_step["loop_context"] = loop
                current_step["variables_before"] = {**current_step.get("variables_before", {}), **state}
                current_step["variables_after"] = {**current_step.get("variables_after", {}), **state}
    latest_state: dict[str, str] = {}
    for index, step in enumerate(steps):
        if not step.get("variables_after"):
            step["variables_after"] = dict(step.get("variables_before") or latest_state)
        condition = conditions.get(step["line"])
        if condition:
            next_line = next((later["line"] for later in steps[index + 1 :] if later["line"] != step["line"]), None)
            result = _line_in_ranges(next_line, condition.get("body_ranges", []))
            state_for_condition = step.get("variables_before") or latest_state
            step["condition"] = {
                "expression": condition["expression"],
                "result": result,
                "reason": _condition_reason(condition, state_for_condition, result),
            }
        after = step.get("variables_after") or step.get("variables_before") or {}
        if after:
            latest_state = dict(after)
    for index, step in enumerate(steps):
        info = step.get("function_return")
        if not info:
            continue
        function = info.get("function")
        next_step = next((later for later in steps[index + 1 :] if later.get("function_context") != function), None)
        if next_step:
            info["next_line"] = next_step.get("line")
    for index, step in enumerate(steps):
        step["index"] = index
        step["total_steps"] = len(steps)
    return steps


def _ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _changed_variable_sentence(change: dict[str, Any]) -> str:
    name, old, new = change.get("name") or "value", change.get("old"), change.get("new")
    return f"{name} was set to {new}." if old in {"", None} else f"{name} changed from {old} to {new}."


def _step_loop_sentence(step: dict[str, Any]) -> str:
    loop = step.get("loop_context") or {}
    if not loop:
        return ""
    text = (
        f"You are on the {_ordinal(int(loop.get('iteration') or 1))} time through the loop on line {loop.get('line')}"
    )
    if loop.get("target") and loop.get("target_value") is not None:
        text += f"; {loop.get('target')} is {loop.get('target_value')}"
    return text + "."


def _format_name_values(items: list[dict[str, Any]]) -> str:
    return ", ".join(f"{item.get('name')} gets {item.get('value')}" for item in items if item.get("name"))


def _function_call_sentence(call: dict[str, Any]) -> str:
    function = call.get("function") or "the function"
    values = _format_name_values(call.get("parameters") or [])
    return f"You are entering the function {function}." + (f" {values}." if values else "")


def _local_variables_sentence(locals_map: dict[str, Any], parameters: list[dict[str, Any]] | None = None) -> str:
    if not locals_map:
        return ""
    param_names = {item.get("name") for item in parameters or []}
    items = [(name, value) for name, value in locals_map.items() if name not in param_names] or list(locals_map.items())
    return "Local values: " + ", ".join(f"{name} is {value}" for name, value in items[:6]) + "."


def _call_stack_sentence(step: dict[str, Any]) -> str:
    stack = step.get("function_call_stack") or []
    function = step.get("function_context") or (stack[-1].get("function") if stack else "")
    if not function:
        return ""
    caller = stack[-2].get("function") if len(stack) >= 2 else (stack[-1].get("caller") if stack else "")
    return f"You are inside {function}" + (f", called by {caller}." if caller else ".")


def _function_return_sentence(return_info: dict[str, Any]) -> str:
    sentence = f"Function {return_info.get('function') or 'the function'} returned {return_info.get('return_value')}"
    if return_info.get("call_line"):
        sentence += f" to line {return_info.get('call_line')}"
    if return_info.get("next_line"):
        sentence += f", then Python continues at line {return_info.get('next_line')}"
    return sentence + "."


def _nearest_function_step(steps: list[dict[str, Any]], cursor: int, kind: str = "any") -> dict[str, Any] | None:
    checks = {
        "call": lambda s: s.get("function_call"),
        "context": lambda s: s.get("function_context"),
        "return": lambda s: s.get("function_return"),
        "any": lambda s: s.get("function_call") or s.get("function_context") or s.get("function_return"),
    }
    check = checks.get(kind, checks["any"])
    candidates = list(steps[max(0, cursor) :]) + list(reversed(steps[: max(0, cursor)]))
    return next((step for step in candidates if check(step)), None)


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
        if str(step.get("source") or "").lstrip().startswith(("for ", "while ")):
            parts.append(f"This is the loop on line {step['line']}.")
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
