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


_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

_VAR_FROM_QUERY = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*document\."
    r"(?:getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)|querySelector\(\s*['\"]([^'\"]+)['\"]\s*\))"
)


def _teacher_issue(
    severity: str,
    file: str,
    line: int,
    problem: str,
    why: str,
    fix: str,
    spoken: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "file": file,
        "line": line,
        "problem": problem,
        "why_it_matters": why,
        "suggested_fix": fix,
        "spoken_summary": spoken,
    }


def _selector_to_listener_vars(js: str) -> dict[str, bool]:
    """Map each query selector to whether its variable is later used in addEventListener.

    Detects the common ``const btn = document.getElementById('x'); btn.addEventListener(...)``
    shape so the debugger can explain why a listener silently never fires.
    """
    var_to_selector: dict[str, str] = {}
    for match in _VAR_FROM_QUERY.finditer(js or ""):
        var = match.group(1)
        selector = f"#{match.group(2)}" if match.group(2) else (match.group(3) or "")
        if selector:
            var_to_selector[var] = selector
    listener_vars = set(re.findall(r"\b([A-Za-z_$][\w$]*)\.addEventListener\b", js or ""))
    return {selector: var in listener_vars for var, selector in var_to_selector.items()}


def build_debug_teacher(html: str, css: str = "", js: str = "") -> dict[str, Any]:
    """Beginner-friendly debugger for broken HTML/CSS/JS connections.

    Returns ``{"text": ..., "issues": [...]}`` where each issue has
    ``severity``, ``file``, ``line``, ``problem``, ``why_it_matters``,
    ``suggested_fix`` and ``spoken_summary``. Pure static analysis grounded in
    the source; it never invents runtime errors and never mutates files.
    """
    from codeup.services.selector_tools import did_you_mean, matches
    from codeup.services.web_learning import (
        _selector_should_warn_when_unmatched,
        analyze_javascript,
        parse_css_rules,
        parse_records,
    )
    from codeup.services.website_runner import is_blank_project

    html = html or ""
    js = js or ""

    if is_blank_project(html, css, js):
        message = (
            "WEBSITE DEBUG TEACHER\n\n"
            "There is nothing to debug yet. Build or load a website first, "
            'for example "make a website for my school robotics club".\n'
        )
        return {
            "text": message,
            "speech": "There is nothing to debug yet. Build or load a website first.",
            "issues": [],
        }

    records = parse_records(html)
    js_map = analyze_javascript(js)
    issues: list[dict[str, Any]] = []
    selector_listener = _selector_to_listener_vars(js)

    # 1. JS DOM queries that match no HTML element (the classic broken connection).
    seen_query: set[tuple[str, int]] = set()
    for query in js_map["queries"]:
        selector = query["selector"]
        key = (selector, query["line"])
        if key in seen_query or matches(selector, records):
            continue
        seen_query.add(key)
        suggestion = did_you_mean(selector, records)
        attached = selector_listener.get(selector, False)
        kind = "id" if selector.startswith("#") else "class" if selector.startswith(".") else "selector"
        problem = f"script.js line {query['line']} looks for {selector}, but no HTML element matches that {kind}."
        why = "JavaScript cannot attach behavior to an element it cannot find, so that part of the page does nothing."
        if attached:
            why = (
                "An event listener is attached to the result of this query. Because the query finds nothing, "
                "the listener never fires and the control looks dead."
            )
        if suggestion:
            fix = f"Rename the HTML {kind} to match {selector}, or change the JavaScript to use {suggestion}."
            spoken = f"script.js asks for {selector} but your HTML has {suggestion}. Make them match."
        else:
            fix = (
                f"Add an element whose {kind} is {selector[1:]}, or update the JavaScript selector to one that exists."
            )
            spoken = f"script.js asks for {selector}, but nothing in your HTML matches it."
        issues.append(_teacher_issue("high", "script.js", query["line"], problem, why, fix, spoken))

    # 2. Duplicate ids.
    id_lines: dict[str, list[int]] = {}
    for record in records:
        current = record.attrs.get("id")
        if current:
            id_lines.setdefault(current, []).append(record.line)
    for current, lines in id_lines.items():
        if len(lines) > 1:
            issues.append(
                _teacher_issue(
                    "high",
                    "index.html",
                    lines[1],
                    f'The id "{current}" is used {len(lines)} times in index.html (lines {", ".join(map(str, lines))}).',
                    "Ids must be unique. getElementById only returns the first match, so the others are unreachable.",
                    f'Give each element a unique id, for example "{current}-2".',
                    f"The id {current} is repeated. Make each id unique.",
                )
            )

    # 3. Buttons / forms that look intended to be interactive but have no handler.
    buttons = [record for record in records if record.tag == "button"]
    forms = [record for record in records if record.tag == "form"]
    # Use a regex fallback so single-char variables (b.addEventListener) still count
    # as "a click listener exists" — we only warn when none is present at all.
    has_click_js = bool(re.search(r"addEventListener\(\s*['\"]click['\"]", js, re.IGNORECASE))
    has_submit_js = bool(re.search(r"addEventListener\(\s*['\"]submit['\"]", js, re.IGNORECASE))
    has_click = bool([item for item in js_map["listeners"] if item["event"] == "click"]) or has_click_js
    has_submit = bool([item for item in js_map["listeners"] if item["event"] == "submit"]) or has_submit_js
    if buttons and js.strip() and not has_click and not re.search(r"\bonclick\s*=", html, re.IGNORECASE):
        issues.append(
            _teacher_issue(
                "medium",
                "index.html",
                buttons[0].line,
                "There is at least one button and a script file, but no click listener connects them.",
                "Without a click listener, pressing the button does nothing.",
                "Add button.addEventListener('click', ...) in script.js, using an id that exists in the HTML.",
                "Your button has no click listener, so clicking it does nothing yet.",
            )
        )
    if forms and js.strip() and not has_submit:
        issues.append(
            _teacher_issue(
                "medium",
                "index.html",
                forms[0].line,
                "There is a form and a script file, but no submit listener was found.",
                "Without a submit listener (and preventDefault), the form reloads the page and your JavaScript never runs.",
                "Add form.addEventListener('submit', (event) => { event.preventDefault(); ... }) in script.js.",
                "Your form has no submit listener, so it just reloads the page.",
            )
        )

    # 4. Empty buttons / unnamed controls.
    for record in records:
        if record.tag == "button" and not (record.name or "").strip():
            issues.append(
                _teacher_issue(
                    "medium",
                    "index.html",
                    record.line,
                    f"The button on line {record.line} has no readable label.",
                    "A screen reader announces it as just 'button', so the user cannot tell what it does.",
                    "Add visible text inside the button, or an aria-label that names the action.",
                    "One button has no label. Give it clear text.",
                )
            )

    # 5. Buttons inside a form with no type (default submit can surprise beginners).
    form_ranges = [(form.line, form.depth) for form in forms]
    if form_ranges:
        for record in buttons:
            in_form = any(record.line >= line and record.depth > depth for line, depth in form_ranges)
            if in_form and not record.attrs.get("type"):
                issues.append(
                    _teacher_issue(
                        "low",
                        "index.html",
                        record.line,
                        f"The button on line {record.line} is inside a form but has no type attribute.",
                        "A button with no type defaults to type=submit, which can submit the form unexpectedly.",
                        'Add type="button" for normal buttons, or type="submit" if it is meant to submit.',
                        "A button in your form has no type, so it may submit the form by accident.",
                    )
                )
                break

    # 6. Links with href="#" and no click handler.
    onclick_in_html = bool(re.search(r"\bonclick\s*=", html, re.IGNORECASE))
    for record in records:
        if record.tag == "a" and record.attrs.get("href", "").strip() == "#" and not has_click and not onclick_in_html:
            issues.append(
                _teacher_issue(
                    "low",
                    "index.html",
                    record.line,
                    f'The link on line {record.line} points to "#" and has no click handler.',
                    "A link to # jumps to the top of the page and does nothing useful.",
                    "Point the link at a real URL or section id, or use a button with a click listener instead.",
                    "A link points to nowhere. Give it a real destination.",
                )
            )
            break

    # 7. CSS selectors that match nothing.
    for rule in parse_css_rules(css):
        selector = rule["selector"]
        if matches(selector, records):
            continue
        if not _selector_should_warn_when_unmatched(selector):
            continue
        suggestion = did_you_mean(selector.strip().split()[-1] if selector.strip() else selector, records)
        fix = "Remove the unused rule, or fix the selector so it matches an element."
        if suggestion:
            fix = f"Did you mean {suggestion}? Update the selector or the HTML so they match."
        issues.append(
            _teacher_issue(
                "low",
                "style.css",
                rule["line"],
                f"CSS line {rule['line']} styles {selector}, but no HTML element matches it.",
                "A rule that matches nothing has no effect and usually means a typo or leftover code.",
                fix,
                f"The CSS rule {selector} matches nothing in your HTML.",
            )
        )

    issues.sort(key=lambda item: (_SEVERITY_RANK.get(item["severity"], 9), item["line"]))
    issues = issues[:12]

    if not issues:
        text = (
            "WEBSITE DEBUG TEACHER\n\n"
            "I read your HTML, CSS, and JavaScript and did not find a broken connection. "
            "Selectors match elements, ids are unique, and controls look wired up. "
            "Open the live preview and try the buttons to confirm.\n"
        )
        speech = (
            "I did not find any broken connections. Selectors match, ids are unique, and your controls are wired up."
        )
        return {"text": text, "speech": speech, "issues": []}

    blocks = ["WEBSITE DEBUG TEACHER", "", "I read your files; I did not run them. Here is what I found:", ""]
    for index, issue in enumerate(issues, start=1):
        blocks.extend(
            [
                f"{index}. [{issue['severity'].upper()}] {issue['file']} line {issue['line']}",
                f"Problem: {issue['problem']}",
                f"Why it matters: {issue['why_it_matters']}",
                f"Fix: {issue['suggested_fix']}",
                "",
            ]
        )
    blocks.append('Say "fix website error" to apply the safe fixes I can make automatically.')

    # Short spoken summary: the count plus the most important issue.
    top = issues[0]
    plural = "issue" if len(issues) == 1 else "issues"
    more = "" if len(issues) == 1 else f" The other {len(issues) - 1} are on screen."
    speech = f"I found {len(issues)} {plural}. Most important: {top['spoken_summary']}{more}"
    return {"text": "\n".join(blocks).strip() + "\n", "speech": speech, "issues": issues}


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
