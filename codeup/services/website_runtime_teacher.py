from __future__ import annotations

import re
from typing import Any

from codeup.services.project_type_router import display_project_type
from codeup.services.selector_tools import did_you_mean, matches
from codeup.services.web_learning import analyze_javascript, parse_records
from codeup.services.website_runner import (
    NO_WEBSITE_MESSAGE,
    clean_text,
    has_real_website,
    title_from_html,
)

LANDMARK_TAGS = ("header", "nav", "main", "section", "article", "aside", "footer", "form")


def _control_facts(records: list) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for record in records:
        if record.tag == "button":
            controls.append({"type": "button", "name": clean_text(record.name) or "(no label)", "line": record.line})
        elif record.tag == "a" and record.attrs.get("href") is not None:
            controls.append(
                {
                    "type": "link",
                    "name": clean_text(record.name) or "(no text)",
                    "href": record.attrs.get("href", ""),
                    "line": record.line,
                }
            )
        elif record.tag == "form":
            controls.append({"type": "form", "name": clean_text(record.name) or "form", "line": record.line})
    return controls


def _likely_behavior(js: str, js_map: dict[str, Any], connected: int) -> list[str]:
    behavior: list[str] = []
    lowered = (js or "").lower()
    has_click = any(item["event"] == "click" for item in js_map["listeners"])
    has_submit = any(item["event"] == "submit" for item in js_map["listeners"])
    updates_text = bool(re.search(r"\.(?:textContent|innerHTML|innerText)\s*=", js or ""))
    toggles_class = ".classlist" in lowered
    if has_click and updates_text and connected:
        behavior.append("Clicking a connected button likely changes text on the page.")
    elif has_click and connected:
        behavior.append("Clicking a connected button likely runs JavaScript.")
    if has_submit:
        behavior.append("Submitting the form likely runs JavaScript instead of reloading, if it calls preventDefault.")
    if toggles_class:
        behavior.append("Some JavaScript toggles a CSS class, which likely changes styling (for example a theme).")
    if not behavior:
        if js_map["listeners"]:
            behavior.append("JavaScript is wired to an event, so part of the page likely reacts to the visitor.")
        else:
            behavior.append("No event listeners were found, so this likely behaves as a static, readable page.")
    return behavior


def build_runtime_teacher(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not has_real_website(html):
        return {
            "text": NO_WEBSITE_MESSAGE,
            "speech": NO_WEBSITE_MESSAGE,
            "facts": {
                "title": "",
                "headings": [],
                "controls": [],
                "queries": [],
                "listeners": [],
                "mismatches": [],
            },
        }

    records = parse_records(html)
    title = title_from_html(html, name or "this website")
    landmarks = [record for record in records if record.tag in LANDMARK_TAGS]
    headings = [record for record in records if re.fullmatch(r"h[1-6]", record.tag)]
    js_map = analyze_javascript(js)
    controls = _control_facts(records)

    heading_facts = [
        {
            "level": int(record.tag[1]),
            "tag": record.tag,
            "text": clean_text(record.text) or "(no text)",
            "line": record.line,
        }
        for record in headings
    ]

    query_facts: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for query in js_map["queries"]:
        selector = query["selector"]
        matched = bool(matches(selector, records))
        query_facts.append({"method": query["method"], "selector": selector, "line": query["line"], "matched": matched})
        if not matched:
            suggestion = did_you_mean(selector, records)
            reason = f"No HTML element matches {selector}."
            if suggestion:
                reason += f" The closest match in your HTML is {suggestion}; this looks like a typo."
            mismatches.append(
                {"selector": selector, "line": query["line"], "reason": reason, "did_you_mean": suggestion}
            )

    listener_facts = [dict(item) for item in js_map["listeners"]]
    connected = sum(1 for query in query_facts if query["matched"])

    facts = {
        "title": title,
        "headings": heading_facts,
        "controls": controls,
        "queries": query_facts,
        "listeners": listener_facts,
        "mismatches": mismatches,
    }

    type_label = display_project_type(project_type or "generic_website")
    buttons = [control for control in controls if control["type"] == "button"]
    links = [control for control in controls if control["type"] == "link"]
    forms = [control for control in controls if control["type"] == "form"]

    lines = [
        "WEBSITE RUNTIME TEACHER",
        "",
        "This is a static check. I read your files; I did not click anything.",
        f"When the page loads, the browser shows {type_label.lower()}: {title}.",
    ]
    if landmarks:
        lines.append("Landmarks in reading order: " + ", ".join(record.tag for record in landmarks) + ".")
    else:
        lines.append("I did not find landmark regions, so screen reader navigation by region will be hard.")
    if heading_facts:
        lines.append(
            "Headings in order: "
            + "; ".join(f"{item['tag'].upper()} {item['text']}" for item in heading_facts[:8])
            + "."
        )
    else:
        lines.append("I did not find any headings, so there is no outline to skim.")

    control_bits = []
    if buttons:
        control_bits.append(f"{len(buttons)} button(s): " + ", ".join(item["name"] for item in buttons[:5]))
    if links:
        control_bits.append(f"{len(links)} link(s)")
    if forms:
        control_bits.append(f"{len(forms)} form(s)")
    lines.append("Controls I found: " + (", ".join(control_bits) if control_bits else "none") + ".")

    if listener_facts:
        for item in listener_facts[:5]:
            lines.append(f"In script.js, line {item['line']} adds a {item['event']} listener to {item['target']}.")
    else:
        lines.append("I found no JavaScript event listeners.")

    if query_facts:
        for query in query_facts[:6]:
            if query["matched"]:
                lines.append(
                    f"script.js line {query['line']} looks for {query['selector']}, and that matches an element in "
                    "index.html, so the connection is in place."
                )
            else:
                detail = next((m["reason"] for m in mismatches if m["line"] == query["line"]), "")
                lines.append(
                    f"script.js line {query['line']} looks for {query['selector']}, but no HTML element matches it. "
                    f"That part may not work. {detail}".strip()
                )
    else:
        lines.append("I found no DOM queries in script.js.")

    lines.append("Likely behavior: " + " ".join(_likely_behavior(js, js_map, connected)))

    if mismatches:
        lines.append(
            f"Warning: {len(mismatches)} selector(s) in script.js do not match the HTML. "
            'Say "debug website" for a step-by-step fix.'
        )
    else:
        lines.append('Next, try "debug website" or "is this ready to share".')

    connection_count = len(query_facts)
    if mismatches:
        speech = (
            f"I read your site, {title}. I found {len(buttons)} button and {connection_count} JavaScript connection."
            if len(buttons) == 1 and connection_count == 1
            else f"I read your site, {title}. I found {len(buttons)} buttons and {connection_count} JavaScript connections."
        )
        speech += f' Warning: {len(mismatches)} selector does not match your HTML. Say "debug website" to fix it.'
    elif query_facts:
        speech = (
            f"I read your site, {title}. The JavaScript selectors match your HTML, so the interactions are connected."
        )
    else:
        speech = (
            f"I read your site, {title}. I found {len(buttons)} button(s) and no JavaScript yet, "
            "so this reads as a static page."
        )

    return {"text": "\n".join(lines).strip() + "\n", "speech": speech, "facts": facts}
