from __future__ import annotations

import re
from typing import Any

from codeup.services.html_utils import audit_html
from codeup.services.web_learning import analyze_javascript, parse_css_rules, parse_records


def _has_text(records: list, tags: set[str]) -> bool:
    return any(record.tag in tags and record.text.strip() for record in records)


def _title_has_text(html: str) -> bool:
    match = re.search(r"<title\b[^>]*>(.*?)</title\s*>", html or "", flags=re.I | re.S)
    return bool(match and re.sub(r"<[^>]+>", "", match.group(1)).strip())


def _check_title(html: str, css: str, js: str) -> tuple[bool, str]:
    ok = _title_has_text(html) or _has_text(parse_records(html), {"h1"})
    return ok, "page title found" if ok else ""


def _check_heading(html: str, css: str, js: str) -> tuple[bool, str]:
    ok = _has_text(parse_records(html), {"h1"})
    return ok, "main heading found" if ok else ""


def _check_paragraph(html: str, css: str, js: str) -> tuple[bool, str]:
    ok = _has_text(parse_records(html), {"p"})
    return ok, "paragraph found" if ok else ""


def _check_nav(html: str, css: str, js: str) -> tuple[bool, str]:
    ok = any(record.tag == "nav" for record in parse_records(html))
    return ok, "navigation landmark found" if ok else ""


def _check_hero(html: str, css: str, js: str) -> tuple[bool, str]:
    records = parse_records(html)
    has_hero = any(
        "hero" in (record.attrs.get("class", "") + " " + record.attrs.get("id", "")).lower() for record in records
    )
    has_header_heading = any(record.tag == "header" for record in records) and _has_text(records, {"h1", "h2"})
    ok = has_hero or has_header_heading
    return ok, "hero / top section found" if ok else ""


def _check_cards(html: str, css: str, js: str) -> tuple[bool, str]:
    records = parse_records(html)
    has_card = any(
        "card" in (record.attrs.get("class", "") + " " + record.attrs.get("id", "")).lower() for record in records
    )
    section_count = sum(1 for record in records if record.tag in {"section", "article"})
    ok = has_card or section_count >= 2
    return ok, "card / repeated sections found" if ok else ""


def _check_button(html: str, css: str, js: str) -> tuple[bool, str]:
    ok = any(record.tag == "button" for record in parse_records(html))
    return ok, "button found" if ok else ""


def _check_css_layout(html: str, css: str, js: str) -> tuple[bool, str]:
    rules = parse_css_rules(css)
    declarations = " ".join(rule["declarations"] for rule in rules).lower()
    ok = bool(rules) and any(prop in declarations for prop in ("display", "grid", "flex", "gap", "margin", "padding"))
    return ok, "layout CSS found" if ok else ""


def _check_js_behavior(html: str, css: str, js: str) -> tuple[bool, str]:
    lowered = (js or "").lower()
    js_map = analyze_javascript(js)
    has_click = any(item["event"] == "click" for item in js_map["listeners"]) or "click" in lowered
    ok = "addeventlistener" in lowered and has_click
    return ok, "click behavior found" if ok else ""


def _check_run(html: str, css: str, js: str) -> tuple[bool, str]:
    from codeup.services.website_runner import has_real_website

    ok = has_real_website(html)
    return ok, "site is ready to run" if ok else ""


def _check_audit(html: str, css: str, js: str) -> tuple[bool, str]:
    audit = audit_html(html)
    blocking = {"missing_image_alt", "unnamed_button", "missing_form_label", "heading_skip", "low_contrast"}
    remaining = [issue for issue in audit.issues if issue["id"] in blocking]
    ok = not remaining
    return ok, f"accessibility score {audit.score}/100" if ok else ""


def _check_export(html: str, css: str, js: str) -> tuple[bool, str]:
    ok = bool((html or "").strip()) and bool((css or "").strip() or (js or "").strip())
    return ok, "three-file project ready" if ok else ""


GUIDED_STEPS: list[dict[str, Any]] = [
    {
        "id": "title",
        "title": "Add a page title",
        "say": "Every page needs a title. It is the first thing a screen reader announces.",
        "command": "insert page title My First Website",
        "hint": "Say: insert page title, then your website name.",
        "success": "The page now has a title a screen reader can announce.",
        "check": _check_title,
    },
    {
        "id": "heading",
        "title": "Add a main heading",
        "say": "The main heading is the H1. It names what the page is about.",
        "command": "insert heading Welcome",
        "hint": "Say: insert heading, then a short title like Welcome.",
        "success": "Your H1 gives the page a clear top-level heading.",
        "check": _check_heading,
    },
    {
        "id": "paragraph",
        "title": "Add a paragraph",
        "say": "A paragraph holds the readable text under your heading.",
        "command": "insert paragraph This is my first website.",
        "hint": "Say: insert paragraph, then a sentence about your page.",
        "success": "You added readable paragraph text.",
        "check": _check_paragraph,
    },
    {
        "id": "navigation",
        "title": "Add navigation",
        "say": "A navigation landmark lets screen reader users jump between sections.",
        "command": "add navigation",
        "hint": "Say: add navigation, or insert a nav with links.",
        "success": "A nav landmark is in place.",
        "check": _check_nav,
    },
    {
        "id": "hero",
        "title": "Add a hero section",
        "say": "A hero is the welcoming top area with the big heading.",
        "command": "add a hero section",
        "hint": "Say: add a hero section, or wrap your heading in a header.",
        "success": "You have a hero-style top section.",
        "check": _check_hero,
    },
    {
        "id": "cards",
        "title": "Add a card section",
        "say": "Cards group related content into repeatable blocks.",
        "command": "add a card section",
        "hint": "Say: add a card section, or add a second section.",
        "success": "You have card-style sections.",
        "check": _check_cards,
    },
    {
        "id": "button",
        "title": "Add a button",
        "say": "A button is a control a visitor can press.",
        "command": "add a button named Join Team",
        "hint": "Say: add a button, then a clear name like Join Team.",
        "success": "Your page has a button.",
        "check": _check_button,
    },
    {
        "id": "css_layout",
        "title": "Add CSS for layout",
        "say": "CSS arranges the page. A grid or flex layout lines things up.",
        "command": "add card styles",
        "hint": "Try a command that styles layout, cards, or spacing.",
        "success": "Your CSS now controls the layout.",
        "check": _check_css_layout,
    },
    {
        "id": "js_behavior",
        "title": "Add JavaScript button behavior",
        "say": "JavaScript makes the button do something when it is clicked.",
        "command": "add a button interaction",
        "hint": "You need a click listener in script.js for a button that exists.",
        "success": "Your button now has click behavior.",
        "check": _check_js_behavior,
    },
    {
        "id": "run",
        "title": "Run the website teacher",
        "say": "The runtime teacher explains what happens when the page loads.",
        "command": "run website",
        "hint": "Say: run website, to hear a factual walkthrough.",
        "success": "You ran the website teacher.",
        "check": _check_run,
    },
    {
        "id": "audit",
        "title": "Audit accessibility",
        "say": "The audit checks names, labels, headings, alt text, and contrast.",
        "command": "check accessibility",
        "hint": "Say: check accessibility, then fix any blocking issues.",
        "success": "Your page passes the core accessibility checks.",
        "check": _check_audit,
    },
    {
        "id": "export",
        "title": "Export your website",
        "say": "Export downloads your three files plus learning notes.",
        "command": "export website",
        "hint": "Say: export website, to download the ZIP.",
        "success": "Your project is ready to export and share.",
        "check": _check_export,
    },
]

_STEP_INDEX = {step["id"]: index for index, step in enumerate(GUIDED_STEPS)}


def guided_steps() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in step.items() if key != "check"} | {"number": index + 1}
        for index, step in enumerate(GUIDED_STEPS)
    ]


def validate_guided_step(step_id: str, html: str = "", css: str = "", js: str = "") -> dict[str, Any]:
    index = _STEP_INDEX.get(step_id)
    if index is None:
        return {
            "step": step_id,
            "valid": False,
            "message": "Unknown guided step.",
            "hint": "Say: build my first website.",
        }
    step = GUIDED_STEPS[index]
    valid, evidence = step["check"](html or "", css or "", js or "")
    last = index == len(GUIDED_STEPS) - 1
    if valid:
        tail = " You finished the track!" if last else ' Say "next" for the next step.'
        message = f"Success. {step['success']}{tail}"
    else:
        message = f"Not yet. {step['hint']}"
    return {
        "step": step_id,
        "number": index + 1,
        "title": step["title"],
        "valid": valid,
        "message": message,
        "hint": step["hint"],
        "success": step["success"],
        "evidence": evidence,
        "is_last": last,
    }


def guided_recap(html: str = "", css: str = "", js: str = "") -> dict[str, Any]:
    done: list[str] = []
    todo: list[str] = []
    for step in GUIDED_STEPS:
        valid, _ = step["check"](html or "", css or "", js or "")
        (done if valid else todo).append(step["title"])
    next_step = todo[0] if todo else ""
    lines = [
        "GUIDED BUILD RECAP",
        "",
        f"Completed {len(done)} of {len(GUIDED_STEPS)} steps.",
    ]
    if done:
        lines.append("Done: " + ", ".join(done) + ".")
    if next_step:
        lines.append(f"Next up: {next_step}.")
    else:
        lines.append("Every step is complete. Nice work.")
    speech = (
        f"You finished {len(done)} of {len(GUIDED_STEPS)} steps. Next up: {next_step}."
        if next_step
        else f"You finished all {len(GUIDED_STEPS)} steps. Nice work."
    )
    return {
        "text": "\n".join(lines).strip() + "\n",
        "speech": speech,
        "done": done,
        "todo": todo,
        "next": next_step,
        "completed": len(done),
        "total": len(GUIDED_STEPS),
    }
