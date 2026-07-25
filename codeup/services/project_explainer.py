from __future__ import annotations

import re
from typing import Any

from codeup.services.html_utils import audit_html
from codeup.services.project_type_router import display_project_type
from codeup.services.version_history import build_version_history_report
from codeup.services.web_change_review import (
    format_web_change_review,
    latest_review_from_versions,
    review_web_changes,
)
from codeup.services.web_learning import analyze_javascript, build_code_map, parse_css_rules, parse_records
from codeup.services.website_accessibility_lab import (
    build_keyboard_test,
    build_readiness_report,
    build_readiness_score,
    build_screen_reader_tour,
    build_visual_description,
)
from codeup.services.website_debugger import build_debug_report, build_debug_teacher
from codeup.services.website_runner import (
    NO_PROJECT_MESSAGE,
    build_run_summary,
    build_teacher_review,
    is_blank_project,
)


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


_NUMBER_WORDS = {
    0: "no",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def _count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    plural = plural or f"{singular}s"
    word = _NUMBER_WORDS.get(count, str(count))
    return f"{word} {singular if count == 1 else plural}"


def _join_clause(parts: list[str]) -> str:
    parts = [part for part in parts if part]
    if not parts:
        return "nothing yet"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def build_landmarks_summary(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    records = ctx["records"]

    def count(tag: str) -> int:
        return sum(1 for record in records if record.tag == tag)

    headers, navs, mains = count("header"), count("nav"), count("main")
    sections, articles, asides = count("section"), count("article"), count("aside")
    forms, footers = count("form"), count("footer")
    buttons = len([record for record in records if record.tag == "button"])

    spoken_parts: list[str] = []
    if headers:
        spoken_parts.append("a header")
    if navs:
        spoken_parts.append("navigation")
    if mains:
        spoken_parts.append("a main content area")
    if sections:
        spoken_parts.append(_count_phrase(sections, "section"))
    if articles:
        spoken_parts.append(_count_phrase(articles, "article"))
    if asides:
        spoken_parts.append(_count_phrase(asides, "complementary area", "complementary areas"))
    if forms:
        spoken_parts.append(_count_phrase(forms, "contact form" if project_type == "contact_form" else "form"))
    if buttons:
        spoken_parts.append(_count_phrase(buttons, "button"))
    if footers:
        spoken_parts.append("a footer")
    spoken = f"This website has {_join_clause(spoken_parts)}."

    landmark_records = [
        record
        for record in records
        if record.tag in {"header", "nav", "main", "section", "article", "aside", "footer", "form"}
    ]
    lines = [
        f"WEB LANDMARKS: {ctx['name']}",
        "",
        spoken,
        "",
        "Landmarks and sections in reading order:",
    ]
    if landmark_records:
        lines.extend(
            f"- {record.tag}{': ' + _clean_text(record.name) if record.name else ''}" for record in landmark_records
        )
    else:
        lines.append("- no landmark elements found yet")
    lines.extend(
        [
            "",
            f"Forms: {forms}. Buttons: {buttons}. Footer: {'yes' if footers else 'no'}.",
            "Tip: landmarks let screen reader users jump straight to a region instead of reading everything.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_trainer_notes(
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
    concepts = ["Semantic HTML landmarks and a clear heading outline"]
    if ctx["css_rules"]:
        concepts.append("CSS selectors that connect visual style to HTML")
    if ctx["js_map"]["listeners"]:
        concepts.append("JavaScript event listeners that respond to the visitor")
    if ctx["controls"]:
        concepts.append("Labels and names so assistive technology can announce controls")
    discussion = [
        f"How does a screen reader move through {ctx['title']}?",
        "Which heading helps a visitor understand the page first?",
        "Why do buttons and links need readable names?",
    ]
    next_task = "Ask the learner to add one more section and re-run the accessibility check."
    if ctx["project_type"] in {"quiz_app", "calculator_app", "todo_app", "flashcard_app", "poll_page"}:
        next_task = "Ask the learner to add one more interaction and explain it with step narration."
    mistakes = [
        "Images without alt text, or decorative images that should be empty alt.",
        "Buttons or links whose text does not say what they do.",
        "Skipping heading levels (for example h1 then h3).",
    ]
    lines = [
        f"TRAINER NOTES: {ctx['name']}",
        "",
        "Project summary:",
        f"- {ctx['project_type_label']} with {len(ctx['headings'])} headings, "
        f"{len(ctx['sections'])} landmark or section elements, and {len(ctx['controls'])} controls.",
        f"- Latest accessibility score: {ctx['audit'].get('score', 'unknown')}/100.",
        "",
        "Concepts used:",
        *(f"- {item}" for item in concepts),
        "",
        "Accessibility ideas to highlight:",
        "- Semantic landmarks, headings, labels, alt text, visible focus, and readable contrast.",
        "- Encourage testing with the keyboard only and with a screen reader.",
        "",
        "Suggested discussion questions:",
        *(f"- {item}" for item in discussion),
        "",
        f"Suggested next task:\n- {next_task}",
        "",
        "Common mistakes to watch for:",
        *(f"- {item}" for item in mistakes),
    ]
    if issues:
        lines.extend(
            [
                "",
                "Issues from the latest audit to review together:",
                *(
                    f"- {issue.get('severity', 'unknown')}: {issue.get('description', issue.get('id', 'issue'))}"
                    for issue in issues[:5]
                    if isinstance(issue, dict)
                ),
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_student_recap(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
    commands: list[str] | None = None,
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    commands = [str(item).strip() for item in (commands or []) if str(item).strip()][-8:]
    html_concepts = ["You used HTML landmarks and headings to give the page meaning and reading order."]
    css_concepts = (
        ["You used CSS selectors to style the page without changing its meaning."]
        if ctx["css_rules"]
        else ["Next time, try CSS to change colors, spacing, or layout."]
    )
    js_concepts = (
        ["You used JavaScript event listeners so the page responds to clicks or typing."]
        if ctx["js_map"]["listeners"]
        else ["Next time, try a small JavaScript button interaction."]
    )
    a11y_concepts = [
        "You practiced accessibility: labels, alt text, button names, focus, and contrast.",
        f"Your latest accessibility score was {ctx['audit'].get('score', 'unknown')}/100.",
    ]
    lines = [
        f"STUDENT RECAP: {ctx['name']}",
        "",
        f"What you created:\n- A {ctx['project_type_label'].lower()} called {ctx['title']}.",
        "",
        "Commands you used:",
    ]
    if commands:
        lines.extend(f"- {item}" for item in commands)
    else:
        lines.append("- (command history was not recorded this session)")
    lines.extend(
        [
            "",
            "HTML concepts:",
            *(f"- {item}" for item in html_concepts),
            "",
            "CSS concepts:",
            *(f"- {item}" for item in css_concepts),
            "",
            "JavaScript concepts:",
            *(f"- {item}" for item in js_concepts),
            "",
            "Accessibility concepts:",
            *(f"- {item}" for item in a11y_concepts),
            "",
            "Next steps:",
            "- Ask for a code map, edit one section, check accessibility, then export your project.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _concepts_learned(ctx: dict[str, Any]) -> list[str]:
    concepts = ["Semantic HTML landmarks and a heading outline"]
    if ctx["css_rules"]:
        concepts.append("CSS selectors that style HTML without changing meaning")
    if ctx["js_map"]["listeners"]:
        concepts.append("JavaScript event listeners that connect controls to behavior")
    if ctx["controls"]:
        concepts.append("Accessible names and labels for controls")
    concepts.append("Accessibility checking: alt text, labels, focus, and contrast")
    return concepts


def _suggested_next_lesson(ctx: dict[str, Any], readiness: dict[str, Any]) -> str:
    if readiness.get("blockers"):
        return "Accessibility repair: fix the blockers above, then re-run 'is this ready to share'."
    if not ctx["js_map"]["listeners"]:
        return "JavaScript behavior: add a button interaction and explain it with step narration."
    if len(ctx["headings"]) < 2:
        return "Page structure: add another section with its own heading."
    return "Forms and multi-page sites: add a labelled contact form, then a second page."


def build_pilot_report(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
    commands: list[str] | None = None,
    version_history: Any = None,
) -> str:
    if is_blank_project(html, css, js):
        return "PILOT SESSION REPORT\n\n" + NO_PROJECT_MESSAGE + "\n"

    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    commands = [str(item).strip() for item in (commands or []) if str(item).strip()]
    readiness = build_readiness_report(html, css, js, name=name, project_type=project_type, audit=audit)
    mistakes = build_debug_teacher(html, css, js)["issues"]
    fixes = [cmd for cmd in commands if re.search(r"\b(fix|repair|apply|autofix|undo|restore)\b", cmd, re.I)]
    edits = [cmd for cmd in commands if re.search(r"\b(add|insert|change|make|improve|set|edit)\b", cmd, re.I)]
    line_counts = ctx["line_counts"]
    latest_change = latest_review_from_versions(version_history)
    files_created = [
        f"index.html ({line_counts['index.html']} lines)",
        f"style.css ({line_counts['style.css']} lines)",
        f"script.js ({line_counts['script.js']} lines)",
    ]

    lines = [
        f"PILOT SESSION REPORT: {ctx['name']}",
        "",
        f"Project type: {ctx['project_type_label']}.",
        f"Main page title: {ctx['title']}.",
        "",
        "Files created:",
        *(f"- {item}" for item in files_created),
        "",
        f"Accessibility score: {ctx['audit'].get('score', 'unknown')}/100.",
        f"Readiness score: {readiness['score']}/100 ({readiness['level']}).",
        "",
        "Commands used:",
    ]
    if commands:
        lines.extend(f"- {item}" for item in commands[-20:])
    else:
        lines.append("- (command history was not recorded this session)")

    lines.extend(["", "Mistakes found:"])
    if mistakes:
        lines.extend(
            f"- [{issue['severity']}] {issue['file']} line {issue['line']}: {issue['problem']}"
            for issue in mistakes[:8]
        )
    else:
        lines.append("- No broken connections were detected in the final version.")

    lines.extend(["", "Fixes and edits made:"])
    if fixes or edits:
        lines.extend(f"- {item}" for item in (fixes + edits)[:10])
    else:
        lines.append("- No fix or edit commands were recorded.")

    if latest_change and latest_change["changed_files"]:
        lines.extend(
            [
                "",
                "Recent change risk:",
                f"- Changed files: {', '.join(latest_change['changed_files'])}.",
                f"- Risk: {latest_change['risk']}. {latest_change['risk_reason']}",
            ]
        )

    if readiness["blockers"]:
        lines.extend(["", "Blockers still open:", *(f"- {item}" for item in readiness["blockers"])])

    lines.extend(["", "Concepts learned:", *(f"- {item}" for item in _concepts_learned(ctx))])
    lines.extend(["", f"Suggested next lesson:\n- {_suggested_next_lesson(ctx, readiness)}"])
    lines.extend(
        [
            "",
            "Trainer notes:",
            "- Encourage testing with the keyboard only and with a screen reader.",
            "- Revisit any blocker above together before sharing the site publicly.",
            "- Ask the learner to explain one selector connection in their own words.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_screen_reader_summary(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    ctx = project_context(html, css, js, name=name, project_type=project_type, audit=audit)
    records = ctx["records"]
    reading_order = [
        record.tag
        for record in records
        if record.tag in {"header", "nav", "main", "section", "article", "aside", "footer", "form"}
    ]
    headings = [f"{record.tag.upper()} {_clean_text(record.text, record.tag)}" for record in ctx["headings"][:10]]
    links = [record for record in records if record.tag == "a"]
    buttons = [record for record in records if record.tag == "button"]
    forms = [record for record in records if record.tag == "form"]
    issues = ctx["audit"].get("issues") if isinstance(ctx["audit"].get("issues"), list) else []
    heading_lines = [f"- {item}" for item in headings] or ["- no headings found"]
    lines = [
        f"SCREEN READER SUMMARY: {ctx['name']}",
        "",
        f"Project title: {ctx['title']}.",
        "",
        "Reading order (landmarks): " + (", ".join(reading_order) if reading_order else "no landmarks found") + ".",
        "",
        "Heading structure:",
        *heading_lines,
        "",
        f"Forms, buttons, and links: {len(forms)} form(s), {len(buttons)} button(s), {len(links)} link(s).",
        "",
        "Known accessibility issues:",
    ]
    if issues:
        lines.extend(
            f"- {issue.get('severity', 'unknown')}: {issue.get('description', issue.get('id', 'issue'))}"
            for issue in issues[:8]
            if isinstance(issue, dict)
        )
    else:
        lines.append("- none reported in the latest audit")
    lines.extend(
        [
            "",
            "Suggested screen-reader testing path:",
            "1. Read the page top to bottom and confirm the title and main heading make sense.",
            "2. Move by landmarks (header, navigation, main, footer) and by headings.",
            "3. Tab through links, buttons, and form fields; confirm each announces a clear name.",
            "4. Check images announce useful alt text and that focus is always visible.",
            "Recommended tools: NVDA or Narrator on Windows, VoiceOver on macOS; Chrome or Edge.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_change_replay(
    *,
    html_before: str = "",
    html_after: str = "",
    css_before: str = "",
    css_after: str = "",
    js_before: str = "",
    js_after: str = "",
    instruction: str = "",
    provided: str = "",
) -> str:
    if provided.strip():
        body = provided.strip()
    else:
        review = review_web_changes(
            html_before=html_before,
            html_after=html_after,
            css_before=css_before,
            css_after=css_after,
            js_before=js_before,
            js_after=js_after,
        )
        body = format_web_change_review(review)
    header = "CHANGE REPLAY"
    asked = (
        f"You asked: {instruction.strip()}." if instruction.strip() else "Your most recent edit changed the project."
    )
    return f"{header}\n\n{asked}\n\nWhat changed:\n{body}\n".strip() + "\n"


def build_bookmarks_report(bookmarks: Any) -> str:
    lines = ["BOOKMARKS", "", "Saved sections and notes you can revisit:"]
    entries: list[str] = []
    if isinstance(bookmarks, dict):
        for label, value in bookmarks.items():
            detail = ""
            if isinstance(value, dict):
                detail = str(value.get("section") or value.get("issue") or value.get("editor") or "").strip()
            entries.append(f"- {label}{': ' + detail if detail else ''}")
    elif isinstance(bookmarks, list):
        for item in bookmarks:
            if isinstance(item, dict):
                label = str(item.get("name") or item.get("label") or "bookmark").strip()
                detail = str(item.get("section") or item.get("note") or "").strip()
                entries.append(f"- {label}{': ' + detail if detail else ''}")
            elif str(item).strip():
                entries.append(f"- {str(item).strip()}")
    if not entries:
        entries.append("- no bookmarks saved")
    lines.extend(entries)
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
    commands: list[str] | None = None,
    change_replay: dict[str, Any] | None = None,
    bookmarks: Any = None,
    version_history: Any = None,
) -> dict[str, str]:
    provided = provided or {}
    code_map = provided.get("code_map") or build_code_map(html, css, js).get("summary", "")
    artifacts = {
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
        "TRAINER_NOTES.txt": (
            provided.get("trainer_notes")
            or build_trainer_notes(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "STUDENT_RECAP.txt": (
            provided.get("student_recap")
            or build_student_recap(html, css, js, name=name, project_type=project_type, audit=audit, commands=commands)
        ).strip()
        + "\n",
        "SCREEN_READER_SUMMARY.txt": (
            provided.get("screen_reader_summary")
            or build_screen_reader_summary(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "RUN_SUMMARY.txt": (
            provided.get("run_summary")
            or build_run_summary(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "DEBUG_REPORT.txt": (provided.get("debug_report") or build_debug_report(html, css, js)["text"]).strip() + "\n",
        "SCREEN_READER_TOUR.txt": (
            provided.get("screen_reader_tour")
            or build_screen_reader_tour(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "KEYBOARD_TEST.txt": (
            provided.get("keyboard_test")
            or build_keyboard_test(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "VISUAL_DESCRIPTION.txt": (
            provided.get("visual_description")
            or build_visual_description(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "READINESS_SCORE.txt": (
            provided.get("readiness_score")
            or build_readiness_score(html, css, js, name=name, project_type=project_type, audit=audit)
        ).strip()
        + "\n",
        "TEACHER_REVIEW.txt": (
            provided.get("teacher_review")
            or build_teacher_review(html, css, js, name=name, project_type=project_type, audit=audit)["text"]
        ).strip()
        + "\n",
    }

    history_source = provided.get("version_history") or version_history
    if isinstance(history_source, str) and history_source.strip():
        artifacts["VERSION_HISTORY.txt"] = history_source.strip() + "\n"
    elif isinstance(history_source, list) and history_source:
        artifacts["VERSION_HISTORY.txt"] = build_version_history_report(history_source).strip() + "\n"

    replay_text = ""
    if provided.get("change_replay"):
        replay_text = build_change_replay(
            provided=provided["change_replay"], instruction=provided.get("instruction", "")
        )
    elif isinstance(change_replay, dict) and any(
        str(change_replay.get(key) or "").strip()
        for key in ("html_before", "html_after", "css_before", "css_after", "js_before", "js_after")
    ):
        replay_text = build_change_replay(
            html_before=str(change_replay.get("html_before") or ""),
            html_after=str(change_replay.get("html_after") or ""),
            css_before=str(change_replay.get("css_before") or ""),
            css_after=str(change_replay.get("css_after") or ""),
            js_before=str(change_replay.get("js_before") or ""),
            js_after=str(change_replay.get("js_after") or ""),
            instruction=str(change_replay.get("instruction") or ""),
        )
    if replay_text.strip():
        artifacts["CHANGE_REPLAY.txt"] = replay_text.strip() + "\n"

    has_bookmarks = bool(bookmarks) and (
        (isinstance(bookmarks, dict) and len(bookmarks) > 0) or (isinstance(bookmarks, list) and len(bookmarks) > 0)
    )
    if has_bookmarks:
        artifacts["BOOKMARKS.txt"] = build_bookmarks_report(bookmarks).strip() + "\n"

    has_session = bool(commands) or (isinstance(version_history, list) and bool(version_history))
    if provided.get("pilot_report"):
        artifacts["PILOT_REPORT.txt"] = provided["pilot_report"].strip() + "\n"
    elif has_session:
        artifacts["PILOT_REPORT.txt"] = (
            build_pilot_report(
                html,
                css,
                js,
                name=name,
                project_type=project_type,
                audit=audit,
                commands=commands,
                version_history=version_history,
            ).strip()
            + "\n"
        )

    return artifacts
