from __future__ import annotations

import re
from typing import Any

from codeup.services.html_utils import audit_html
from codeup.services.project_type_router import display_project_type
from codeup.services.web_learning import analyze_javascript, build_code_map, parse_css_rules, parse_records


def _clean_text(value: str, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text or fallback


def _title_from_html(html: str, fallback: str) -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1\s*>", html or "", flags=re.I | re.S)
    if match:
        return _clean_text(re.sub(r"<[^>]+>", " ", match.group(1)), fallback)
    match = re.search(r"<title\b[^>]*>(.*?)</title\s*>", html or "", flags=re.I | re.S)
    if match:
        return _clean_text(re.sub(r"<[^>]+>", " ", match.group(1)), fallback)
    return fallback


def _line_count(value: str) -> int:
    stripped = (value or "").strip()
    return len(stripped.splitlines()) if stripped else 0


def _audit_dict(html: str, audit: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(audit, dict) and "score" in audit:
        return audit
    return audit_html(html).to_dict()


def project_context(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    title = _title_from_html(html, name or "CodeUp Web project")
    records = parse_records(html)
    headings = [record for record in records if re.fullmatch(r"h[1-6]", record.tag)]
    sections = [record for record in records if record.tag in {"header", "nav", "main", "section", "article", "footer"}]
    controls = [record for record in records if record.tag in {"button", "a", "input", "textarea", "select", "form"}]
    images = [record for record in records if record.tag == "img"]
    css_rules = parse_css_rules(css)
    js_map = analyze_javascript(js)
    audit_data = _audit_dict(html, audit)
    return {
        "name": name or title,
        "title": title,
        "project_type": project_type or "generic_website",
        "project_type_label": display_project_type(project_type or "generic_website"),
        "records": records,
        "headings": headings,
        "sections": sections,
        "controls": controls,
        "images": images,
        "css_rules": css_rules,
        "js_map": js_map,
        "audit": audit_data,
        "line_counts": {"index.html": _line_count(html), "style.css": _line_count(css), "script.js": _line_count(js)},
    }


def build_project_summary(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    listeners = ctx["js_map"]["listeners"]
    functions = ctx["js_map"]["functions"]
    lines = [
        f"PROJECT SUMMARY: {ctx['name']}",
        "",
        f"Type: {ctx['project_type_label']}.",
        f"Main page: {ctx['title']}.",
        (
            f"Files: index.html has {ctx['line_counts']['index.html']} lines, style.css has "
            f"{ctx['line_counts']['style.css']} lines, and script.js has {ctx['line_counts']['script.js']} lines."
        ),
        (
            f"Structure: {len(ctx['headings'])} headings, {len(ctx['sections'])} landmark or section elements, "
            f"and {len(ctx['controls'])} controls."
        ),
        f"Behavior: {len(functions)} JavaScript functions and {len(listeners)} event listeners.",
        f"Accessibility: latest score {ctx['audit'].get('score', 'unknown')}/100.",
    ]
    if ctx["headings"]:
        lines.append(
            "Top headings: " + "; ".join(_clean_text(item.text, item.tag) for item in ctx["headings"][:5]) + "."
        )
    return "\n".join(lines).strip() + "\n"


def build_step_narration(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    first_heading = _clean_text(ctx["headings"][0].text, ctx["title"]) if ctx["headings"] else ctx["title"]
    listeners = ctx["js_map"]["listeners"]
    steps = [
        f"STEP NARRATION: {ctx['name']}",
        "",
        "1. The browser opens index.html and reads the document title, language, and page structure.",
        f"2. The visitor reaches the main heading: {first_heading}.",
        f"3. The browser loads style.css, which applies {len(ctx['css_rules'])} visible style rules.",
        "4. The browser loads script.js with defer, so behavior starts after the HTML is ready.",
    ]
    if listeners:
        event_text = ", ".join(f"{item['target']} on {item['event']}" for item in listeners[:5])
        steps.append(f"5. JavaScript waits for interaction: {event_text}.")
        steps.append("6. When the visitor clicks or types, the page updates text on screen without leaving the page.")
    else:
        steps.append("5. No custom JavaScript behavior was found, so the page works as a readable static website.")
    steps.append(
        "7. Accessibility checks focus on headings, labels, button names, image alt text, focus styles, and contrast."
    )
    return "\n".join(steps).strip() + "\n"


def build_file_explanation(
    filename: str,
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
) -> str:
    target = (filename or "").lower()
    ctx = project_context(html, css, js, name=name, project_type=project_type)
    if target in {"css", "style", "style.css"}:
        selectors = ", ".join(rule["selector"] for rule in ctx["css_rules"][:8]) or "no selectors yet"
        return (
            "STYLE.CSS EXPLANATION\n\n"
            f"This file controls the visual design for {ctx['name']}. It has {ctx['line_counts']['style.css']} lines. "
            f"Important selectors include: {selectors}. Keep focus styles and readable contrast when editing it.\n"
        )
    if target in {"js", "javascript", "script", "script.js"}:
        functions = (
            ", ".join(item["name"] + "()" for item in ctx["js_map"]["functions"][:8]) or "no named functions yet"
        )
        listeners = (
            ", ".join(f"{item['event']} listener" for item in ctx["js_map"]["listeners"][:8])
            or "no event listeners yet"
        )
        return (
            "SCRIPT.JS EXPLANATION\n\n"
            f"This file adds behavior for {ctx['name']}. It has {ctx['line_counts']['script.js']} lines. "
            f"Functions: {functions}. Events: {listeners}. It should avoid network calls, eval, secrets, and redirects.\n"
        )
    heading_text = "; ".join(_clean_text(item.text, item.tag) for item in ctx["headings"][:8]) or "no headings yet"
    return (
        "INDEX.HTML EXPLANATION\n\n"
        f"This file gives {ctx['name']} its meaning and reading order. It has "
        f"{ctx['line_counts']['index.html']} lines. Main headings: {heading_text}. "
        "Use semantic landmarks, labels, alt text, and buttons with readable names.\n"
    )


def build_learning_notes(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    concepts = [
        "HTML landmarks create a screen-reader friendly reading order.",
        "Headings describe the outline before a visitor reads every paragraph.",
        "CSS selectors connect visual style to HTML elements.",
        "Visible focus styles help keyboard users see where they are.",
    ]
    if ctx["js_map"]["listeners"]:
        concepts.append("JavaScript event listeners make buttons and forms respond to the visitor.")
    if ctx["controls"]:
        concepts.append("Forms and controls need labels or names so assistive technology can announce them.")
    issues = ctx["audit"].get("issues") if isinstance(ctx["audit"].get("issues"), list) else []
    if issues:
        concepts.append("Accessibility audits are a normal editing step; fix high-impact issues first.")
    lines = [f"LEARNING NOTES: {ctx['name']}", "", f"Project type: {ctx['project_type_label']}.", ""]
    lines.extend(f"- {item}" for item in concepts)
    return "\n".join(lines).strip() + "\n"


def build_accessibility_map(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    issues = ctx["audit"].get("issues") if isinstance(ctx["audit"].get("issues"), list) else []
    lines = [
        f"ACCESSIBILITY MAP: {ctx['name']}",
        "",
        f"Score: {ctx['audit'].get('score', 'unknown')}/100.",
        f"Landmarks and sections: {len(ctx['sections'])}.",
        f"Headings: {len(ctx['headings'])}.",
        f"Controls and forms: {len(ctx['controls'])}.",
        f"Images: {len(ctx['images'])}; missing alt text: {sum(1 for image in ctx['images'] if not image.attrs.get('alt', '').strip())}.",
        f"Focus style found: {'yes' if ':focus' in css or ':focus-visible' in css else 'not obvious'}.",
        "",
    ]
    if issues:
        lines.append("Issues to review:")
        lines.extend(
            f"- {issue.get('severity', 'unknown')}: {issue.get('description', issue.get('id', 'Unknown issue'))}"
            for issue in issues[:8]
            if isinstance(issue, dict)
        )
    else:
        lines.append("No structured accessibility issues were reported.")
    return "\n".join(lines).strip() + "\n"


def build_project_review(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    issues = ctx["audit"].get("issues") if isinstance(ctx["audit"].get("issues"), list) else []
    strengths: list[str] = []
    if ctx["headings"]:
        strengths.append("It has a readable heading outline.")
    if ctx["sections"]:
        strengths.append("It uses landmarks or sections for navigation.")
    if ctx["js_map"]["listeners"]:
        strengths.append("It includes in-page JavaScript interaction.")
    if ":focus" in css or ":focus-visible" in css:
        strengths.append("It includes keyboard focus styling.")
    next_steps: list[str] = []
    if issues:
        next_steps.extend(
            issue.get("suggested_fix") or issue.get("description") or "Review one accessibility issue."
            for issue in issues[:3]
            if isinstance(issue, dict)
        )
    if not ctx["js_map"]["listeners"]:
        next_steps.append("Add a small button or form interaction in script.js.")
    if len(ctx["headings"]) < 2:
        next_steps.append("Add one more section heading so the page is easier to scan.")
    if not next_steps:
        next_steps.append("Preview it, export it, and ask another person to try the main workflow.")
    lines = [
        f"PROJECT REVIEW: {ctx['name']}",
        "",
        "Strengths:",
        *(f"- {item}" for item in strengths[:5] or ["The project has a clear starting point."]),
        "",
        "Recommended next steps:",
        *(f"- {item}" for item in next_steps[:5]),
    ]
    return "\n".join(lines).strip() + "\n"


def build_preview_description(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type)
    headings = [_clean_text(item.text, item.tag) for item in ctx["headings"][:6]]
    controls = [_clean_text(item.name, item.tag) for item in ctx["controls"][:6]]
    css_text = " ".join(rule["selector"] for rule in ctx["css_rules"][:8])
    tone = "styled with custom CSS" if ctx["css_rules"] else "plain and lightly styled"
    if "hero" in css_text.lower():
        tone = "starts with a hero-style top area"
    lines = [
        f"PREVIEW DESCRIPTION: {ctx['name']}",
        "",
        f"A visitor first sees {ctx['title']}. The page is {tone}.",
        f"The visible outline includes: {', '.join(headings) if headings else 'no headings found'}.",
        f"Interactive controls include: {', '.join(controls) if controls else 'none found'}.",
    ]
    if ctx["js_map"]["listeners"]:
        lines.append("The preview responds to clicks or form actions without opening another page.")
    return "\n".join(lines).strip() + "\n"


def build_export_artifacts(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
    provided: dict[str, str] | None = None,
) -> dict[str, str]:
    provided = provided or {}
    code_map = provided.get("code_map") or build_code_map(html, css, js).get("summary", "")
    return {
        "CODE_MAP.txt": code_map.strip() + "\n",
        "STEP_NARRATION.txt": (
            provided.get("step_narration")
            or build_step_narration(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "LEARNING_NOTES.txt": (
            provided.get("learning_notes")
            or build_learning_notes(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "PROJECT_SUMMARY.txt": (
            provided.get("project_summary")
            or build_project_summary(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "ACCESSIBILITY_REPORT.txt": (
            provided.get("accessibility_map")
            or build_accessibility_map(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "PROJECT_REVIEW.txt": (
            provided.get("project_review")
            or build_project_review(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "PREVIEW_DESCRIPTION.txt": (
            provided.get("preview_description")
            or build_preview_description(html, css, js, name=name, project_type=project_type)
        ).strip()
        + "\n",
    }
