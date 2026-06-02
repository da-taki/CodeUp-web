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
ELEMENT_WATCHPOINT_IDS = {"unnamed_button", "unnamed_link", "missing_form_label"}


def _is_descendant_of(node: HtmlNode, ancestor: HtmlNode) -> bool:
    parent = node.parent
    while parent:
        if parent is ancestor:
            return True
        parent = parent.parent
    return False


def _inline_style_hides(node: HtmlNode) -> bool:
    style = re.sub(r"\s+", "", node.attrs.get("style", "").lower())
    return "display:none" in style or "visibility:hidden" in style


def _is_hidden_from_focus(node: HtmlNode) -> bool:
    current: HtmlNode | None = node
    while current:
        if "hidden" in current.attrs:
            return True
        if current.attrs.get("aria-hidden", "").strip().lower() == "true":
            return True
        if _inline_style_hides(current):
            return True
        current = current.parent
    return False


def _tabindex_value(node: HtmlNode) -> int | None:
    raw = node.attrs.get("tabindex")
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _is_disabled_control(node: HtmlNode) -> bool:
    return node.tag in {"button", "input", "textarea", "select"} and "disabled" in node.attrs


def _is_focusable_node(node: HtmlNode) -> bool:
    if _is_hidden_from_focus(node) or _is_disabled_control(node):
        return False

    tabindex = _tabindex_value(node)
    if tabindex is not None and tabindex < 0:
        return False

    tag = node.tag
    role = node.attrs.get("role", "").strip().lower()
    has_keyboard_tabindex = tabindex is not None and tabindex >= 0

    if tag == "a":
        return bool(node.attrs.get("href")) or (has_keyboard_tabindex and role in {"button", "link"})
    if tag == "input":
        return node.attrs.get("type", "text").strip().lower() != "hidden"
    if tag in {"button", "textarea", "select", "summary"}:
        return True
    if role in {"button", "link"} and has_keyboard_tabindex:
        return True
    return has_keyboard_tabindex


def _focusable_role(node: HtmlNode) -> str:
    role = node.attrs.get("role", "").strip().lower()
    if role in {"button", "link"}:
        return role
    if node.tag == "a":
        return "link"
    if node.tag == "button":
        return "button"
    if node.tag == "input":
        input_type = node.attrs.get("type", "text").strip().lower() or "text"
        return f"{input_type} input"
    if node.tag == "textarea":
        return "text area"
    if node.tag == "select":
        return "dropdown menu"
    if node.tag == "summary":
        return "summary"
    return role or node.tag


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
            nav_node = next(
                (
                    node
                    for node in all_nodes
                    if node.tag == "nav"
                    and (node.attrs.get("aria-label") or node.attrs.get("aria-labelledby") or "") == label
                ),
                None,
            )
            nav_links = []
            for node in links:
                if nav_node and _is_descendant_of(node, nav_node):
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


def _collect_focusable(html: str) -> list[dict[str, Any]]:
    root = parse_html(html)
    issues = [
        issue
        for issue in audit_html(html).issues
        if issue["severity"] in ("high", "medium") and issue["id"] in ELEMENT_WATCHPOINT_IDS
    ]
    issues_by_selector: dict[str, dict[str, Any]] = {issue["selector"]: issue for issue in issues}
    records: list[tuple[int, int, dict[str, Any]]] = []

    for dom_index, node in enumerate(iter_nodes(root)):
        if not _is_focusable_node(node):
            continue
        name = accessible_name(node)
        role = _focusable_role(node)
        selector = node.selector()
        watchpoint = issues_by_selector.get(selector)
        record: dict[str, Any] = {
            "tag": node.tag,
            "role": role,
            "name": name or "unnamed",
            "label": f"{role}, {name}" if name else f"{role}, unnamed",
            "selector": selector,
        }
        tabindex = _tabindex_value(node)
        if tabindex is not None:
            record["tabindex"] = tabindex
        if watchpoint:
            record["watchpoint_ids"] = [watchpoint["id"]]
            record["watchpoint"] = {
                "id": watchpoint["id"],
                "description": watchpoint["description"],
                "selector": watchpoint["selector"],
                "suggested_fix": watchpoint["suggested_fix"],
                "autofix": watchpoint.get("autofix", False),
            }
        records.append((tabindex or 0, dom_index, record))

    records.sort(key=lambda item: (0 if item[0] > 0 else 1, item[0] if item[0] > 0 else item[1], item[1]))
    return [record for _, _, record in records[:MAX_FOCUSABLE]]


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

    fixed_html, fixed_ids, audit_after = apply_audit_fixes(
        html, issue_id=issue["id"], issue_selector=issue.get("selector")
    )

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

    for index, (img_before, img_after) in enumerate(
        zip(iter_nodes(root_before, {"img"}), iter_nodes(root_after, {"img"}), strict=False), 1
    ):
        alt_before = img_before.attrs.get("alt", "")
        alt_after = img_after.attrs.get("alt", "")
        if (not alt_before or alt_before == "Describe this image") and alt_after and alt_after != alt_before:
            changes.append(f'Image {index} now has alternative text: "{alt_after}".')

    control_tags = {"button", "a", "input", "textarea", "select"}
    before_controls = [node for node in iter_nodes(root_before, control_tags)]
    after_controls = [node for node in iter_nodes(root_after, control_tags)]
    for index, (before_control, after_control) in enumerate(zip(before_controls, after_controls, strict=False), 1):
        before_name = accessible_name(before_control)
        after_name = accessible_name(after_control)
        if before_name or not after_name:
            continue
        role = _focusable_role(after_control)
        changes.append(f'{role.capitalize()} {index} now has readable label: "{after_name}".')

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
