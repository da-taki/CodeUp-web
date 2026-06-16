"""Run / test website summaries and teacher-style reviews.

Deterministic, beginner-friendly reports built from the current HTML/CSS/JS using
the same parsing and audit helpers that power the rest of CodeUp Web. Nothing here
mutates project files.
"""

from __future__ import annotations

import re
from typing import Any

from codeup.services.html_utils import audit_html
from codeup.services.project_type_router import display_project_type
from codeup.services.web_learning import analyze_javascript, parse_css_rules, parse_records

LANDMARK_TAGS = {"header", "nav", "main", "section", "article", "aside", "footer", "form"}


def clean_text(value: str, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text or fallback


def title_from_html(html: str, fallback: str = "this website") -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1\s*>", html or "", flags=re.I | re.S)
    if match:
        return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)), fallback)
    match = re.search(r"<title\b[^>]*>(.*?)</title\s*>", html or "", flags=re.I | re.S)
    if match:
        return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)), fallback)
    return fallback


def has_real_website(html: str) -> bool:
    """True when the HTML looks like a generated site, not an empty editor."""
    records = parse_records(html)
    has_landmark = any(record.tag in LANDMARK_TAGS for record in records)
    has_heading = any(re.fullmatch(r"h[1-6]", record.tag) for record in records)
    text = re.sub(r"<[^>]+>", " ", html or "")
    return bool(has_landmark or has_heading) and len(clean_text(text)) > 20


NO_WEBSITE_MESSAGE = 'I can test a website after you create one. Try "make a website for my school robotics club."'


def _likely_actions(records: list, js_map: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if any(record.tag == "button" for record in records):
        actions.append("click buttons")
    if any(record.tag == "a" for record in records):
        actions.append("follow links")
    if any(record.tag == "form" for record in records):
        actions.append("fill in a form")
    if any(record.tag in {"input", "textarea", "select"} for record in records):
        actions.append("type into fields")
    if js_map["listeners"]:
        actions.append("see the page react without reloading")
    return actions or ["read the content"]


def build_run_summary(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    if not has_real_website(html):
        return NO_WEBSITE_MESSAGE

    records = parse_records(html)
    headings = [record for record in records if re.fullmatch(r"h[1-6]", record.tag)]
    sections = [record for record in records if record.tag in {"section", "article"}]
    buttons = [record for record in records if record.tag == "button"]
    links = [record for record in records if record.tag == "a"]
    forms = [record for record in records if record.tag == "form"]
    js_map = analyze_javascript(js)
    interactive = bool(js_map["listeners"] or js_map["functions"])
    audit_data = audit if isinstance(audit, dict) and "score" in audit else audit_html(html).to_dict()
    issues = audit_data.get("issues") if isinstance(audit_data.get("issues"), list) else []
    title = title_from_html(html, name or "this website")
    type_label = display_project_type(project_type or "generic_website")

    lines = [
        "WEBSITE RUN SUMMARY",
        "",
        f"Your website loaded as {type_label.lower()}: {title}.",
        (
            f"It has {len(sections)} section(s), {len(headings)} heading(s), {len(buttons)} button(s), "
            f"{len(links)} link(s), and {len(forms)} form(s)."
        ),
        "HTML is present." if (html or "").strip() else "No HTML yet.",
        "CSS is present, so the page has styling." if (css or "").strip() else "No CSS yet, so the page is unstyled.",
        (
            "JavaScript is present, so some parts may be interactive."
            if interactive
            else "No interactive JavaScript was found, so this reads as a static page."
        ),
        f"Likely actions: {', '.join(_likely_actions(records, js_map))}.",
    ]

    if issues:
        top = "; ".join(
            clean_text(str(issue.get("description") or issue.get("id") or "issue"))
            for issue in issues[:3]
            if isinstance(issue, dict)
        )
        lines.append(f"Obvious issues to look at: {top}.")
    else:
        lines.append("No obvious accessibility issues were reported.")

    lines.append(
        'Next, try "screen reader tour" to hear the reading order, or "test keyboard navigation" '
        "to check if buttons and forms are reachable."
    )
    return "\n".join(lines).strip() + "\n"


def build_teacher_review(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return teacher-style feedback. Suggestions are advice only — nothing is changed."""
    records = parse_records(html)
    headings = [record for record in records if re.fullmatch(r"h[1-6]", record.tag)]
    sections = [record for record in records if record.tag in {"section", "article"}]
    forms = [record for record in records if record.tag == "form"]
    js_map = analyze_javascript(js)
    css_rules = parse_css_rules(css)
    audit_data = audit if isinstance(audit, dict) and "score" in audit else audit_html(html).to_dict()
    issues = audit_data.get("issues") if isinstance(audit_data.get("issues"), list) else []
    title = title_from_html(html, name or "your website")

    strengths: list[str] = []
    if headings:
        strengths.append("It has a clear heading outline that screen readers can follow.")
    if sections:
        strengths.append("It uses sections to group related content.")
    if css_rules:
        strengths.append("It includes CSS, so the page has its own visual style.")
    if js_map["listeners"]:
        strengths.append("It adds JavaScript interaction with event listeners.")
    if ":focus" in (css or "") or ":focus-visible" in (css or ""):
        strengths.append("It defines a visible keyboard focus style.")
    if not strengths:
        strengths.append("It has a clear starting point you can build on.")

    suggestions: list[str] = []
    for issue in issues[:3]:
        if isinstance(issue, dict):
            fix = clean_text(str(issue.get("suggested_fix") or issue.get("description") or ""))
            if fix:
                suggestions.append(fix)
    if len(headings) < 2:
        suggestions.append("Add one more section heading so the page is easier to scan.")
    if not forms and project_type in {"contact_form", "generic_website", "school_club", "portfolio"}:
        suggestions.append("Consider adding a labelled contact form so visitors can reach you.")
    if not js_map["listeners"]:
        suggestions.append("Try a small button interaction in script.js to make the page feel alive.")
    if not suggestions:
        suggestions.append("Add more specific button and link text so each action is clear.")
    suggestions = suggestions[:3]

    learn_next = "headings and landmarks" if len(headings) < 2 else "labels and alt text for accessibility"
    if js_map["listeners"]:
        learn_next = "how event listeners connect buttons to behavior"

    lines = [
        f"TEACHER REVIEW: {title}",
        "",
        "Three strengths:",
        *(f"- {item}" for item in strengths[:3]),
        "",
        "Three things to improve:",
        *(f"{index}. {item}" for index, item in enumerate(suggestions, start=1)),
        "",
        f"What to learn next: {learn_next}.",
        "",
        'Suggested commands: "check accessibility", "screen reader tour", "test keyboard navigation".',
        "",
        'You can say "apply the first suggestion" or "make these improvements" when you are ready.',
    ]
    return {"text": "\n".join(lines).strip() + "\n", "suggestions": suggestions, "strengths": strengths[:3]}
