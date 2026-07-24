from __future__ import annotations

import ast
import builtins
import csv
import datetime
import json
import math
import random
import statistics
import string
import sys
import time
import traceback

# Keep the sandbox import surface explicit; do not expose filesystem, network, or process modules.
SAFE_MODULES = {
    "math": math,
    "random": random,
    "statistics": statistics,
    "string": string,
    "datetime": datetime,
    "json": json,
    "csv": csv,
}

FORBIDDEN_NAMES = {
    "__subclasses__",
    "__bases__",
    "__mro__",
    "__class__",
    "__globals__",
    "__builtins__",
    "__import__",
    "__loader__",
    "__spec__",
    "__getattribute__",
    "__reduce__",
    "__reduce_ex__",
    "__dict__",
    "__code__",
    "__base__",
    "__new__",
    "__self__",
    "__func__",
    "__closure__",
    "mro",
    "f_globals",
    "f_locals",
    "f_builtins",
    "f_code",
    "tb_frame",
    "gi_frame",
    "cr_frame",
    "ag_frame",
}

FORBIDDEN_CALLS = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "dir",
    "vars",
    "globals",
    "locals",
    "breakpoint",
    "__import__",
}

TRACE_LIMIT = 5000
VALUE_LIMIT = 200
OUTPUT_LIMIT = 20_000
MAX_RANGE_ABS = 1_000_000
MAX_REPEAT_FACTOR = 100_000
MAX_LITERAL_ITEMS = 5000

_input_queue: list[str] = []
_input_index = 0
_input_events: list[dict[str, object]] = []
_output_chars = 0


class CodeUpOutputLimitError(RuntimeError):
    pass


def _top_level(name: str) -> str:
    return str(name or "").split(".", 1)[0]


def _safe_import(name, globals_arg=None, locals_arg=None, fromlist=(), level=0):
    if level:
        raise ImportError("Relative imports are not available in CodeUp Web Python mode.")
    top = _top_level(name)
    if top not in SAFE_MODULES:
        raise ImportError(f"Module '{name}' is not available in CodeUp Web Python mode.")
    if fromlist:
        for item in fromlist:
            if not isinstance(item, str) or item.startswith("_") or item in FORBIDDEN_NAMES:
                raise ImportError(f"Import of '{item}' is not allowed.")
    return SAFE_MODULES[top]


def _audit_ast(source: str) -> None:
    tree = ast.parse(source or "")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _top_level(alias.name) not in SAFE_MODULES:
                    raise SyntaxError(f"Module '{alias.name}' is not available in CodeUp Web Python mode.")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise SyntaxError("Relative imports are not available in CodeUp Web Python mode.")
            if _top_level(node.module or "") not in SAFE_MODULES:
                raise SyntaxError(f"Module '{node.module}' is not available in CodeUp Web Python mode.")
            for alias in node.names:
                if alias.name.startswith("_") or alias.name in FORBIDDEN_NAMES:
                    raise SyntaxError(f"Import of '{alias.name}' is not allowed.")
        elif isinstance(node, ast.Attribute) and (node.attr in FORBIDDEN_NAMES or node.attr.startswith("_")):
            raise SyntaxError(f"Access to '{node.attr}' is not allowed.")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise SyntaxError(f"Reference to '{node.id}' is not allowed.")
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)) and len(node.elts) > MAX_LITERAL_ITEMS:
            raise SyntaxError("That literal has too many items for CodeUp Web Python mode.")
        elif isinstance(node, ast.Dict) and len(node.keys) > MAX_LITERAL_ITEMS:
            raise SyntaxError("That dictionary has too many items for CodeUp Web Python mode.")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            sides = (node.left, node.right)
            for side in sides:
                if (
                    isinstance(side, ast.Constant)
                    and isinstance(side.value, int)
                    and abs(side.value) > MAX_REPEAT_FACTOR
                ):
                    raise SyntaxError("That repeat count is too large for CodeUp Web Python mode.")
        elif isinstance(node, ast.Call):
            func = node.func
            func_name = ""
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            if func_name in FORBIDDEN_CALLS and func_name != "input":
                raise SyntaxError(f"Use of '{func_name}' is not available in CodeUp Web Python mode.")
            if func_name == "range":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and abs(arg.value) > MAX_RANGE_ABS:
                        raise SyntaxError("That range is too large to run safely in CodeUp Web Python mode.")
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value in FORBIDDEN_NAMES:
                    raise SyntaxError(f"Reflective access to '{arg.value}' is not allowed.")


def _load_inputs(path: str) -> None:
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                _input_queue.append(line.rstrip("\r\n"))
    except OSError as exc:
        raise RuntimeError(f"Could not load input values: {exc}") from exc


def _queued_input(prompt: str = "") -> str:
    global _input_index
    prompt_text = str(prompt or "")
    if prompt:
        _safe_print(prompt_text, end="")
    if _input_index >= len(_input_queue):
        needed = _input_index + 1
        provided = len(_input_queue)
        _input_events.append({"index": needed, "prompt": prompt_text, "provided": False})
        raise RuntimeError(
            f"Your code asked for input number {needed}, but only {provided} value(s) were provided. "
            "Add input values before running."
        )
    value = _input_queue[_input_index]
    _input_events.append({"index": _input_index + 1, "prompt": prompt_text, "value": value, "provided": True})
    _input_index += 1
    _safe_print(value)
    return value


def _safe_repr(value) -> str:
    try:
        text = repr(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    if len(text) > VALUE_LIMIT:
        return text[: VALUE_LIMIT - 3] + "..."
    return text


def _safe_print(*values, sep: str = " ", end: str = "\n", file=None, flush: bool = False) -> None:
    global _output_chars
    if file not in {None, sys.stdout}:
        raise RuntimeError("Printing to files is not available in CodeUp Web Python mode.")
    text = sep.join(str(value) for value in values) + end
    if _output_chars + len(text) > OUTPUT_LIMIT:
        remaining = max(0, OUTPUT_LIMIT - _output_chars)
        if remaining:
            builtins.print(text[:remaining], end="", file=sys.stdout, flush=flush)
            _output_chars += remaining
        raise CodeUpOutputLimitError("Your program produced too much output, so CodeUp shortened it.")
    _output_chars += len(text)
    builtins.print(*values, sep=sep, end=end, file=sys.stdout, flush=flush)


SAFE_GLOBALS = {
    "print": _safe_print,
    "range": range,
    "len": len,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "pow": pow,
    "repr": repr,
    "input": _queued_input,
    "math": math,
    "random": random,
    "statistics": statistics,
    "string": string,
    "datetime": datetime,
    "json": json,
    "csv": csv,
}

SAFE_BUILTINS = {
    "None": None,
    "False": False,
    "True": True,
    "isinstance": isinstance,
    "Exception": Exception,
    "BaseException": BaseException,
    "RuntimeError": RuntimeError,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "NameError": NameError,
    "IndexError": IndexError,
    "KeyError": KeyError,
    "ZeroDivisionError": ZeroDivisionError,
    "ImportError": ImportError,
    "AttributeError": AttributeError,
    "StopIteration": StopIteration,
    "object": object,
    "super": super,
    "staticmethod": staticmethod,
    "classmethod": classmethod,
    "property": property,
    "__build_class__": builtins.__build_class__,
    "__import__": _safe_import,
}


def _namespace() -> dict:
    namespace = dict(SAFE_GLOBALS)
    namespace["__builtins__"] = dict(SAFE_BUILTINS)
    namespace["__name__"] = "__main__"
    return namespace


def _run(
    code_file: str,
    trace_file: str,
    inputs_file: str = "",
    output_limit: int = OUTPUT_LIMIT,
    trace_limit: int = TRACE_LIMIT,
) -> int:
    global OUTPUT_LIMIT, TRACE_LIMIT, _output_chars
    OUTPUT_LIMIT = max(1000, int(output_limit or OUTPUT_LIMIT))
    TRACE_LIMIT = max(100, int(trace_limit or TRACE_LIMIT))
    _output_chars = 0
    with open(code_file, encoding="utf-8") as handle:
        source = handle.read()
    _load_inputs(inputs_file)

    trace: list[dict] = []
    last_locals_by_frame: dict[int, dict[str, str]] = {}
    start = time.time()
    namespace = _namespace()
    initial_names = set(namespace)
    overflow_logged = False

    def traceable_locals(frame) -> dict[str, str]:
        current: dict[str, str] = {}
        is_module_frame = frame.f_code.co_name == "<module>"
        for key, value in frame.f_locals.items():
            if is_module_frame and key in initial_names:
                continue
            if key.startswith("__") and key.endswith("__"):
                continue
            current[key] = _safe_repr(value)
        return current

    def tracer(frame, event, arg):
        nonlocal overflow_logged
        if frame.f_code.co_filename != "<user>":
            return tracer
        if len(trace) >= TRACE_LIMIT:
            if not overflow_logged:
                trace.append(
                    {
                        "type": "overflow",
                        "note": "Your program has too many steps to explain all at once.",
                    }
                )
                overflow_logged = True
            return tracer

        if event == "line":
            line = frame.f_lineno
            trace.append(
                {
                    "type": "line_exec",
                    "line": line,
                    "file": "<user>",
                    "function": frame.f_code.co_name,
                    "frame": id(frame),
                }
            )
            frame_key = id(frame)
            previous = last_locals_by_frame.get(frame_key, {})
            current = traceable_locals(frame)
            changes = []
            for key, value in current.items():
                if key not in previous:
                    changes.append(f"{key} initialized to {value}")
                elif previous[key] != value:
                    changes.append(f"{key} changed from {previous[key]} to {value}")
            for key in previous:
                if key not in current:
                    changes.append(f"{key} went out of scope")
            if changes:
                trace.append(
                    {
                        "type": "state_change",
                        "line": line,
                        "file": "<user>",
                        "function": frame.f_code.co_name,
                        "frame": frame_key,
                        "changes": changes,
                    }
                )
            last_locals_by_frame[frame_key] = current
        elif event == "call":
            caller_line = None
            if frame.f_back and frame.f_back.f_code.co_filename == "<user>":
                caller_line = frame.f_back.f_lineno
            trace.append(
                {
                    "type": "call",
                    "function": frame.f_code.co_name,
                    "line": frame.f_lineno,
                    "file": "<user>",
                    "frame": id(frame),
                    "caller_line": caller_line,
                    "locals": traceable_locals(frame) if frame.f_code.co_name != "<module>" else {},
                }
            )
        elif event == "return":
            caller_line = None
            if frame.f_back and frame.f_back.f_code.co_filename == "<user>":
                caller_line = frame.f_back.f_lineno
            trace.append(
                {
                    "type": "return",
                    "file": "<user>",
                    "function": frame.f_code.co_name,
                    "line": frame.f_lineno,
                    "frame": id(frame),
                    "caller_line": caller_line,
                    "value": _safe_repr(arg),
                    "locals": traceable_locals(frame) if frame.f_code.co_name != "<module>" else {},
                }
            )
            last_locals_by_frame.pop(id(frame), None)
        return tracer

    exit_code = 0
    try:
        _audit_ast(source)
        compiled = compile(source, "<user>", "exec")
        sys.settrace(tracer)
        exec(compiled, namespace, namespace)
    except CodeUpOutputLimitError:
        exit_code = 3
        print("CodeUpOutputLimitError: Your program produced too much output, so CodeUp shortened it.", file=sys.stderr)
    except Exception:
        exit_code = 1
        traceback.print_exc(file=sys.stderr)
    finally:
        sys.settrace(None)
        try:
            with open(trace_file, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "trace": trace,
                        "duration_ms": int((time.time() - start) * 1000),
                        "inputs_consumed": _input_index,
                        "input_events": _input_events,
                        "output_truncated": exit_code == 3,
                        "trace_truncated": overflow_logged,
                    },
                    handle,
                )
        except OSError as exc:
            print(f"Could not write trace file: {exc}", file=sys.stderr)
    return exit_code


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "Usage: python_runner.py CODE_FILE TRACE_FILE [INPUTS_FILE] [OUTPUT_LIMIT] [TRACE_LIMIT]", file=sys.stderr
        )
        return 2
    output_limit = int(sys.argv[4]) if len(sys.argv) > 4 else OUTPUT_LIMIT
    trace_limit = int(sys.argv[5]) if len(sys.argv) > 5 else TRACE_LIMIT
    return _run(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3] if len(sys.argv) > 3 else "",
        output_limit=output_limit,
        trace_limit=trace_limit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
