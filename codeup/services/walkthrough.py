from __future__ import annotations

import re
from typing import Any

from codeup.services.html_utils import (
    HtmlNode,
    accessible_name,
    apply_audit_fixes,
    audit_html,
    iter_nodes,
    parse_html,
)

MAX_WATCHPOINTS = 10
MAX_FOCUSABLE = 60

FOCUSABLE_TAGS = {"a", "button", "input", "textarea", "select"}
LANDMARK_TAGS = {"header", "nav", "main", "footer", "section", "article", "form"}


def _node_label(node: HtmlNode) -> str:
    name = accessible_name(node)
    tag = node.tag
    if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
        return f"heading level {tag[1]}, {name or 'unnamed'}"
    role_map = {
        "header": "banner",
        "nav": "navigation",
        "main": "main content",
        "footer": "footer",
        "section": "section",
        "article": "article",
        "form": "form",
        "a": "link",
        "button": "button",
        "img": "image",
        "input": "input",
        "textarea": "text area",
        "select": "dropdown menu",
    }
    role = role_map.get(tag, tag)
    if name:
        return f"{role}, {name}"
    return f"{role}, unnamed"


def page_map(html: str) -> dict[str, Any]:
    if not html or not html.strip():
        return {
            "summary": "There is no current website to walk through yet. Build or open a website first.",
            "landmarks": [],
            "headings": [],
            "links": 0,
            "buttons": 0,
            "images": 0,
            "forms": 0,
            "inputs": 0,
            "watchpoint_count": 0,
        }

    root = parse_html(html)
    all_nodes = iter_nodes(root)

    title_node = None
    for node in all_nodes:
        if node.tag == "title" and node.text:
            title_node = node
            break

    headings = []
    for node in all_nodes:
        if re.fullmatch(r"h[1-6]", node.tag):
            headings.append({"level": int(node.tag[1]), "text": accessible_name(node) or "unnamed"})

    landmarks = []
    for node in all_nodes:
        if node.tag in LANDMARK_TAGS:
            label = node.attrs.get("aria-label") or node.attrs.get("aria-labelledby") or ""
            landmarks.append({"tag": node.tag, "label": label})

    links = iter_nodes(root, {"a"})
    buttons = iter_nodes(root, {"button"})
    images = iter_nodes(root, {"img"})
    forms = iter_nodes(root, {"form"})
    inputs = iter_nodes(root, {"input", "textarea", "select"})

    audit = audit_html(html)
    watchpoints = [i for i in audit.issues if i["severity"] in ("high", "medium")][:MAX_WATCHPOINTS]

    parts = []
    if title_node:
        parts.append(f"Page title: {title_node.text}.")

    parts.append("Page map:")
    if headings:
        h1s = [h for h in headings if h["level"] == 1]
        if h1s:
            parts.append(f"heading level 1, {h1s[0]['text']}.")

    landmark_names = []
    for lm in landmarks[:8]:
        tag = lm["tag"]
        label = lm["label"]
        if tag == "nav":
            nav_links = []
            for node in all_nodes:
                if node.tag == "a" and node.parent and node.parent.tag == "nav":
                    name = accessible_name(node)
                    if name:
                        nav_links.append(name)
            if nav_links:
                landmark_names.append(f"Navigation region with links {', '.join(nav_links[:5])}")
            else:
                landmark_names.append("Navigation region")
        elif tag == "header":
            landmark_names.append("Header region")
        elif tag == "main":
            landmark_names.append("Main content")
        elif tag == "footer":
            landmark_names.append("Footer")
        elif tag == "form":
            landmark_names.append(f"Form{' (' + label + ')' if label else ''}")
        elif tag == "section":
            landmark_names.append(f"Section{' (' + label + ')' if label else ''}")
    if landmark_names:
        parts.append(". ".join(landmark_names) + ".")

    counts = []
    if len(links) > 0:
        counts.append(f"{len(links)} link{'s' if len(links) != 1 else ''}")
    if len(buttons) > 0:
        counts.append(f"{len(buttons)} button{'s' if len(buttons) != 1 else ''}")
    if len(images) > 0:
        counts.append(f"{len(images)} image{'s' if len(images) != 1 else ''}")
    if len(forms) > 0:
        counts.append(f"{len(forms)} form{'s' if len(forms) != 1 else ''}")
    if len(inputs) > 0:
        counts.append(f"{len(inputs)} form input{'s' if len(inputs) != 1 else ''}")
    if counts:
        parts.append("Contains " + ", ".join(counts) + ".")

    if watchpoints:
        wp_count = len(watchpoints)
        parts.append(
            f"I found {wp_count} accessibility watchpoint{'s' if wp_count != 1 else ''}: "
            f"{watchpoints[0]['description']}"
        )
        parts.append(
            'Say "start keyboard journey" to explore focus order, or "explain first issue" to understand the watchpoint.'
        )

    return {
        "summary": " ".join(parts),
        "landmarks": landmarks[:8],
        "headings": headings[:20],
        "links": len(links),
        "buttons": len(buttons),
        "images": len(images),
        "forms": len(forms),
        "inputs": len(inputs),
        "watchpoint_count": len(watchpoints),
    }


def _collect_focusable(html: str) -> list[dict[str, str]]:
    root = parse_html(html)
    elements: list[dict[str, str]] = []

    def visit(node: HtmlNode) -> None:
        if node.tag in FOCUSABLE_TAGS:
            name = accessible_name(node)
            role_map = {
                "a": "link",
                "button": "button",
                "input": "input",
                "textarea": "text area",
                "select": "dropdown menu",
            }
            input_type = node.attrs.get("type", "text") if node.tag == "input" else ""
            role = role_map.get(node.tag, node.tag)
            if node.tag == "input" and input_type:
                role = f"{input_type} input"
            elements.append(
                {
                    "tag": node.tag,
                    "role": role,
                    "name": name or "unnamed",
                    "label": f"{role}, {name}" if name else f"{role}, unnamed",
                }
            )
        tabindex = node.attrs.get("tabindex", "")
        role_attr = node.attrs.get("role", "")
        if node.tag not in FOCUSABLE_TAGS and tabindex not in ("", "-1") and role_attr in ("button", "link"):
            name = accessible_name(node)
            elements.append(
                {
                    "tag": node.tag,
                    "role": role_attr,
                    "name": name or "unnamed",
                    "label": f"{role_attr}, {name}" if name else f"{role_attr}, unnamed",
                }
            )
        for child in node.children:
            visit(child)

    visit(root)
    return elements[:MAX_FOCUSABLE]


def keyboard_journey_start(html: str) -> dict[str, Any]:
    if not html or not html.strip():
        return {
            "message": "There is no current website to walk through yet. Build or open a website first.",
            "elements": [],
            "index": -1,
            "total": 0,
        }
    elements = _collect_focusable(html)
    if not elements:
        return {
            "message": "No interactive elements found on this page. The page has no links, buttons, or form inputs.",
            "elements": [],
            "index": -1,
            "total": 0,
        }
    first = elements[0]
    return {
        "message": f"Keyboard journey started. First interactive element: {first['label']}. "
        f"There are {len(elements)} interactive elements total.",
        "elements": elements,
        "index": 0,
        "total": len(elements),
    }


def keyboard_journey_move(html: str, current_index: int, direction: str = "next") -> dict[str, Any]:
    elements = _collect_focusable(html)
    if not elements:
        return {"message": "No interactive elements found.", "index": -1, "total": 0, "element": None}

    if direction == "previous":
        new_index = max(0, current_index - 1)
    else:
        new_index = min(len(elements) - 1, current_index + 1)

    el = elements[new_index]
    at_boundary = ""
    if new_index == 0 and direction == "previous":
        at_boundary = " You are at the beginning of the keyboard journey."
    elif new_index == len(elements) - 1 and direction == "next":
        at_boundary = " You have reached the last interactive element."

    prefix = "Next" if direction == "next" else "Previous"
    return {
        "message": f"{prefix} interactive element: {el['label']}.{at_boundary}",
        "index": new_index,
        "total": len(elements),
        "element": el,
    }


def list_watchpoints(html: str) -> dict[str, Any]:
    if not html or not html.strip():
        return {
            "message": "There is no current website to walk through yet. Build or open a website first.",
            "watchpoints": [],
            "count": 0,
        }
    audit = audit_html(html)
    issues = audit.issues[:MAX_WATCHPOINTS]
    if not issues:
        return {
            "message": "No accessibility watchpoints found. The page passes all current checks.",
            "watchpoints": [],
            "count": 0,
            "score": audit.score,
        }

    lines = [f"Found {len(issues)} accessibility watchpoint{'s' if len(issues) != 1 else ''}:"]
    for i, issue in enumerate(issues, 1):
        lines.append(f"{i}. {issue['description']}")

    return {
        "message": "\n".join(lines),
        "watchpoints": issues,
        "count": len(issues),
        "score": audit.score,
    }


def explain_watchpoint(html: str, issue_index: int = 0) -> dict[str, Any]:
    if not html or not html.strip():
        return {"message": "There is no current website to walk through yet. Build or open a website first."}
    audit = audit_html(html)
    issues = audit.issues[:MAX_WATCHPOINTS]
    if not issues:
        return {"message": "No accessibility watchpoints found on this page."}
    if issue_index < 0 or issue_index >= len(issues):
        issue_index = 0
    issue = issues[issue_index]

    explanations: dict[str, str] = {
        "missing_image_alt": (
            "An image is missing alternative text. A blind visitor using a screen reader "
            "will know an image exists but will not learn what it shows. "
            "Adding descriptive alt text lets everyone understand the image content."
        ),
        "unnamed_button": (
            "A button has no readable label. A screen reader user will hear "
            "something like 'button' with no indication of what it does. "
            "Adding visible text or an aria-label makes the button understandable."
        ),
        "unnamed_link": (
            "A link has no readable text. A screen reader user navigating by links "
            "will not know where this link goes. Adding link text fixes this."
        ),
        "missing_form_label": (
            "A form input has no associated label. A screen reader user will not know "
            "what information to enter. Adding a label element or aria-label fixes this."
        ),
        "heading_skip": (
            "Heading levels skip in a way that can confuse keyboard and screen reader navigation. "
            "Screen reader users often skim by headings, and skipped levels suggest missing content."
        ),
        "missing_h1": (
            "The page has no main heading (h1). Screen reader users rely on the h1 "
            "to understand the page topic. Adding one helps orientation."
        ),
        "missing_landmarks": (
            "The page does not use semantic landmark sections like main, nav, header, or footer. "
            "Screen reader users use landmarks to jump between page regions."
        ),
        "missing_lang": (
            "The HTML element has no language attribute. Screen readers use this to choose "
            "the correct pronunciation. Without it, speech may be unintelligible."
        ),
        "missing_title": (
            "The page has no readable title. The title is the first thing a screen reader announces "
            "when the page loads, helping users know where they are."
        ),
        "low_contrast": (
            "At least one text and background color pair does not meet WCAG AA contrast requirements. "
            "Low contrast makes text harder to read for users with low vision."
        ),
    }

    explanation = explanations.get(
        issue["id"],
        f"Accessibility watchpoint: {issue['description']} Suggested fix: {issue['suggested_fix']}",
    )

    return {
        "message": f"Accessibility watchpoint: {issue['description']} {explanation}",
        "issue": issue,
        "issue_index": issue_index,
        "can_autofix": issue.get("autofix", False),
    }


def fix_current_issue(html: str, issue_index: int = 0) -> dict[str, Any]:
    if not html or not html.strip():
        return {"message": "There is no current website to walk through yet.", "fixed_html": "", "success": False}

    audit_before = audit_html(html)
    issues = audit_before.issues[:MAX_WATCHPOINTS]
    if not issues:
        return {"message": "No accessibility issues to fix.", "fixed_html": html, "success": False}

    if issue_index < 0 or issue_index >= len(issues):
        issue_index = 0
    issue = issues[issue_index]

    if not issue.get("autofix"):
        return {
            "message": (
                f"The issue '{issue['description']}' cannot be fixed automatically. "
                f"Suggested manual fix: {issue['suggested_fix']}"
            ),
            "fixed_html": html,
            "success": False,
            "issue": issue,
        }

    fixed_html, fixed_ids, audit_after = apply_audit_fixes(html, issue_id=issue["id"])

    if not fixed_ids:
        return {
            "message": f"Could not apply the fix for: {issue['description']}.",
            "fixed_html": html,
            "success": False,
            "issue": issue,
        }

    return {
        "message": f"Fixed: {issue['description']}",
        "fixed_html": fixed_html,
        "fixed_ids": fixed_ids,
        "success": True,
        "issue": issue,
        "score_before": audit_before.score,
        "score_after": audit_after.score,
    }


def compare_before_after(html_before: str, html_after: str) -> dict[str, Any]:
    if not html_before or not html_after:
        return {"message": "Cannot compare: no before or after version available.", "changes": []}

    audit_before = audit_html(html_before)
    audit_after = audit_html(html_after)

    before_ids = {i["id"] for i in audit_before.issues}
    after_ids = {i["id"] for i in audit_after.issues}
    fixed_ids = before_ids - after_ids
    new_ids = after_ids - before_ids

    changes = []

    root_before = parse_html(html_before)
    root_after = parse_html(html_after)

    for img_after in iter_nodes(root_after, {"img"}):
        alt_after = img_after.attrs.get("alt", "")
        if alt_after and alt_after != "Describe this image":
            for img_before in iter_nodes(root_before, {"img"}):
                alt_before = img_before.attrs.get("alt", "")
                if not alt_before or alt_before == "Describe this image":
                    changes.append(
                        f'An image now has alternative text: "{alt_after}" (previously missing or placeholder).'
                    )
                    break

    for issue_id in sorted(fixed_ids):
        before_issue = next((i for i in audit_before.issues if i["id"] == issue_id), None)
        if before_issue:
            changes.append(f"Fixed: {before_issue['description']}")

    for issue_id in sorted(new_ids):
        after_issue = next((i for i in audit_after.issues if i["id"] == issue_id), None)
        if after_issue:
            changes.append(f"New issue: {after_issue['description']}")

    parts = []
    if changes:
        parts.extend(changes[:8])
    else:
        parts.append("No significant accessibility changes detected between the two versions.")

    score_changed = audit_before.score != audit_after.score
    if score_changed:
        parts.append(
            f"The accessibility audit score changed from {audit_before.score} to {audit_after.score} out of 100."
        )

    remaining = len(audit_after.issues)
    if remaining > 0:
        parts.append(f"{remaining} issue{'s' if remaining != 1 else ''} remaining.")
    else:
        parts.append("All detected accessibility issues have been resolved.")

    return {
        "message": " ".join(parts),
        "changes": changes,
        "score_before": audit_before.score,
        "score_after": audit_after.score,
        "issues_before": len(audit_before.issues),
        "issues_after": len(audit_after.issues),
    }
