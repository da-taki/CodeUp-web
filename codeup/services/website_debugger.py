"""Beginner-friendly, honest static debugging for generated websites.

Inspects HTML/CSS/JS for likely problems and explains them like a teacher. Findings
are grounded in the source — it never invents runtime errors. The architecture keeps
a single ``collect_issues`` pass so real preview-console capture can be layered on
later by merging extra issue dicts into the same shape.
"""

from __future__ import annotations

import re
from typing import Any

UNSAFE_JS = re.compile(
    r"\beval\s*\(|new\s+Function\s*\(|document\.write\s*\(|\bsetTimeout\s*\(\s*['\"]",
    re.IGNORECASE,
)


def _ids_in_html(html: str) -> list[str]:
    return re.findall(r"\bid\s*=\s*['\"]([\w-]+)['\"]", html or "", flags=re.IGNORECASE)


def _ids_referenced_by_js(js: str) -> list[str]:
    refs = re.findall(r"getElementById\(\s*['\"]([\w-]+)['\"]", js or "")
    refs += re.findall(r"querySelector(?:All)?\(\s*['\"]#([\w-]+)", js or "")
    return refs


def _balanced(js: str) -> tuple[bool, int]:
    pairs = {"(": ")", "[": "]", "{": "}"}
    closers = {value: key for key, value in pairs.items()}
    stack: list[tuple[str, int]] = []
    in_string: str | None = None
    for index, char in enumerate(js or ""):
        line = js[:index].count("\n") + 1
        if in_string:
            if char == in_string and js[index - 1 : index] != "\\":
                in_string = None
            continue
        if char in "'\"`":
            in_string = char
            continue
        if char in pairs:
            stack.append((char, line))
        elif char in closers:
            if not stack or stack[-1][0] != closers[char]:
                return False, line
            stack.pop()
    if stack:
        return False, stack[-1][1]
    return True, 0


def collect_issues(html: str, css: str = "", js: str = "") -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    html = html or ""
    js = js or ""

    present_ids = _ids_in_html(html)
    present_set = set(present_ids)

    # Missing DOM ids referenced by JavaScript.
    for ref in dict.fromkeys(_ids_referenced_by_js(js)):
        if ref not in present_set:
            issues.append(
                {
                    "id": "missing_dom_id",
                    "problem": f'JavaScript is looking for an element with id "{ref}", but index.html does not contain that id.',
                    "why": "The code cannot connect to the element, so that part of the page may do nothing.",
                    "fix": f'Either add id="{ref}" to the matching element, or change the JavaScript to use an id that exists.',
                }
            )

    # Duplicate ids.
    seen: set[str] = set()
    for current in present_ids:
        if current in seen:
            issues.append(
                {
                    "id": "duplicate_id",
                    "problem": f'The id "{current}" is used more than once in index.html.',
                    "why": "Ids must be unique; getElementById only returns the first match, so behavior can be confusing.",
                    "fix": f'Give each element a unique id, for example "{current}-2".',
                }
            )
            break
        seen.add(current)

    # Unsafe JavaScript patterns.
    if UNSAFE_JS.search(js):
        issues.append(
            {
                "id": "unsafe_js",
                "problem": "The JavaScript uses an unsafe pattern such as eval, new Function, document.write, or a string timer.",
                "why": "These patterns can run untrusted code or rewrite the page, which is risky and hard to debug.",
                "fix": "Replace eval/new Function with normal functions, and update the DOM with textContent or elements instead of document.write.",
            }
        )

    # Likely infinite loop.
    if re.search(r"\bwhile\s*\(\s*true\s*\)", js) and "break" not in js:
        issues.append(
            {
                "id": "infinite_loop",
                "problem": "There is a while(true) loop with no break, which may run forever.",
                "why": "An infinite loop freezes the page so nothing else can run.",
                "fix": "Add a clear stop condition or a break statement inside the loop.",
            }
        )
    if re.search(r"\bfor\s*\(\s*;\s*;\s*\)", js):
        issues.append(
            {
                "id": "infinite_loop",
                "problem": "There is a for(;;) loop, which has no stop condition.",
                "why": "A loop with no stop condition can run forever and freeze the page.",
                "fix": "Add a stop condition to the for loop.",
            }
        )

    # JavaScript bracket / syntax balance.
    balanced, line = _balanced(js)
    if not balanced:
        issues.append(
            {
                "id": "js_syntax",
                "problem": f"The JavaScript brackets do not balance near line {line}.",
                "why": "Unbalanced (), [], or {} is a syntax error, so the whole script may fail to run.",
                "fix": "Check that every opening bracket has a matching closing bracket near that line.",
            }
        )

    # Interactivity expected but no handlers.
    has_button = bool(re.search(r"<button\b", html, re.IGNORECASE))
    has_form = bool(re.search(r"<form\b", html, re.IGNORECASE))
    has_listener = "addeventlistener" in js.lower() or re.search(r"\bon[a-z]+\s*=", html, re.IGNORECASE)
    if (has_button or has_form) and js.strip() and not has_listener:
        issues.append(
            {
                "id": "missing_handler",
                "problem": "There are buttons or a form, and a script file, but no event handler connects them.",
                "why": "Without an event listener, clicking the button or submitting the form may do nothing.",
                "fix": "Add an addEventListener for the button or form in script.js.",
            }
        )

    # Form submit that reloads the page.
    if has_form and "addeventlistener" in js.lower() and "preventdefault" not in js.lower():
        issues.append(
            {
                "id": "form_reload",
                "problem": "A form has JavaScript, but no event.preventDefault() was found.",
                "why": "Without preventDefault, submitting the form reloads the page and may lose the user's input.",
                "fix": "Call event.preventDefault() at the start of the submit handler.",
            }
        )

    # Dynamic output without an aria-live region.
    updates_dom = bool(re.search(r"\.(?:textContent|innerHTML)\s*=", js))
    if updates_dom and "aria-live" not in html.lower():
        issues.append(
            {
                "id": "missing_aria_live",
                "problem": "JavaScript updates text on the page, but no element has aria-live.",
                "why": "Screen reader users will not hear dynamic updates unless the changing area is a live region.",
                "fix": 'Add aria-live="polite" to the element whose text changes (for example a result or status area).',
            }
        )

    return issues


def build_debug_report(html: str, css: str = "", js: str = "") -> dict[str, Any]:
    issues = collect_issues(html, css, js)
    if not issues:
        message = (
            "WEBSITE DEBUG REPORT\n\n"
            "I did not find obvious website errors. Try running the site in a browser and testing the buttons.\n"
        )
        return {"text": message, "issues": []}

    blocks = ["WEBSITE DEBUG REPORT", ""]
    for issue in issues[:8]:
        blocks.extend(
            [
                f"Problem:\n{issue['problem']}",
                "",
                f"Why it matters:\n{issue['why']}",
                "",
                f"Suggested fix:\n{issue['fix']}",
                "",
            ]
        )
    blocks.append('If a fix is safe, say "fix website error" and I will apply what I safely can.')
    return {"text": "\n".join(blocks).strip() + "\n", "issues": issues[:8]}


def apply_safe_js_fixes(html: str, css: str = "", js: str = "") -> dict[str, Any]:
    """Apply only safe, deterministic fixes. Never introduces unsafe code."""
    fixed_html = html or ""
    changes: list[str] = []

    present = set(_ids_in_html(fixed_html))
    referenced = [ref for ref in dict.fromkeys(_ids_referenced_by_js(js)) if ref not in present]

    # Safe fix: when JS references a single missing id and exactly one obvious target
    # element has no id, attach the referenced id to that element.
    for ref in referenced:
        candidates = list(
            re.finditer(r"<(button|form|input|textarea|select)\b(?![^>]*\bid=)[^>]*>", fixed_html, re.IGNORECASE)
        )
        if len(candidates) == 1:
            match = candidates[0]
            tag = match.group(1)
            replacement = match.group(0).replace(f"<{tag}", f'<{tag} id="{ref}"', 1)
            fixed_html = fixed_html[: match.start()] + replacement + fixed_html[match.end() :]
            present.add(ref)
            changes.append(f'Added id="{ref}" to the <{tag}> element so the JavaScript can find it.')

    # Never let a "fix" introduce unsafe patterns.
    if UNSAFE_JS.search(fixed_html):
        fixed_html = html or ""
        changes = []

    if not changes:
        summary = ["No safe automatic fix was available. Open the debug report and fix the issues by hand."]
    else:
        summary = changes
    return {
        "html": fixed_html,
        "css": css or "",
        "js": js or "",
        "changed": bool(changes),
        "summary": summary,
        "message": "WEBSITE DEBUG FIX\n\n" + "\n".join(f"- {item}" for item in summary) + "\n",
    }
