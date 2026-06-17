"""Accessibility lab: screen-reader tour, keyboard test, visual description, readiness.

All reports are deterministic and read-only — they describe the current HTML/CSS/JS
and never modify project files.
"""

from __future__ import annotations

import re
from typing import Any

from codeup.services.html_utils import audit_html
from codeup.services.web_learning import parse_css_rules, parse_records
from codeup.services.website_debugger import collect_issues
from codeup.services.website_runner import NO_PROJECT_MESSAGE, clean_text, is_blank_project, title_from_html

VAGUE_LINK_WORDS = {"click here", "here", "learn more", "read more", "more", "link", "this", "go", "click"}
FOCUSABLE_TAGS = {"a", "button", "input", "select", "textarea"}


def _lang_attr(html: str) -> str:
    match = re.search(r"<html\b[^>]*\blang\s*=\s*['\"]([\w-]+)['\"]", html or "", re.IGNORECASE)
    return match.group(1) if match else ""


def _label_for(record) -> str:
    return clean_text(record.attrs.get("aria-label") or record.attrs.get("alt") or record.text)


def build_screen_reader_tour(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    records = parse_records(html)
    title = title_from_html(html, name or "this website")
    lang = _lang_attr(html)
    landmarks = [
        r for r in records if r.tag in {"header", "nav", "main", "section", "article", "aside", "footer", "form"}
    ]
    headings = [r for r in records if re.fullmatch(r"h[1-6]", r.tag)]
    links = [r for r in records if r.tag == "a"]
    buttons = [r for r in records if r.tag == "button"]
    fields = [r for r in records if r.tag in {"input", "textarea", "select"}]
    images = [r for r in records if r.tag == "img"]
    live = [r for r in records if r.attrs.get("aria-live")]

    lines = [
        "SCREEN READER TOUR",
        "",
        f"A screen reader would likely start with the page title: {title}.",
        f"The page language is set to '{lang}'."
        if lang
        else "Warning: the page is missing a language attribute on <html>.",
    ]
    if landmarks:
        lines.append("Landmarks in order: " + ", ".join(r.tag for r in landmarks) + ".")
    else:
        lines.append("No landmark regions were found, so navigation by region will be hard.")
    if headings:
        lines.append(
            "Heading order: " + "; ".join(f"{r.tag.upper()} {_label_for(r) or r.tag}" for r in headings[:10]) + "."
        )
    else:
        lines.append("No headings were found, so there is no outline to jump through.")
    lines.append(
        "Links in order: " + (", ".join(_label_for(r) or "(no text)" for r in links[:8]) or "none found") + "."
    )
    lines.append(
        "Buttons in order: " + (", ".join(_label_for(r) or "(no label)" for r in buttons[:8]) or "none found") + "."
    )
    if fields:
        lines.append(
            "Form controls in order: " + ", ".join(_label_for(r) or f"{r.tag} (no label)" for r in fields[:8]) + "."
        )
    else:
        lines.append("No form controls were found.")
    if images:
        described = sum(1 for r in images if r.attrs.get("alt", "").strip())
        lines.append(
            f"Images: {len(images)} total, {described} with alt text, {len(images) - described} missing alt text."
        )
    if live:
        lines.append(f"Live regions: {len(live)} element(s) will announce updates automatically.")

    warnings: list[str] = []
    for record in links + buttons:
        label = _label_for(record).lower()
        if not label:
            warnings.append(f"A {record.tag} has no readable text. Add clear text or an aria-label.")
        elif label in VAGUE_LINK_WORDS:
            kind = "link" if record.tag == "a" else "button"
            warnings.append(
                f'The {kind} "{clean_text(_label_for(record))}" is vague. Consider naming what it does, '
                f'for example "Learn more about robotics projects."'
            )
    if warnings:
        lines.append("")
        lines.append("Warning:")
        lines.extend(f"- {item}" for item in warnings[:6])

    return "\n".join(lines).strip() + "\n"


def build_keyboard_test(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    records = parse_records(html)
    focusable = []
    for record in records:
        if record.tag in FOCUSABLE_TAGS:
            if record.tag == "a" and not record.attrs.get("href"):
                continue
            if record.attrs.get("tabindex") == "-1":
                continue
            focusable.append(record)
        elif record.attrs.get("tabindex") and record.attrs.get("tabindex") != "-1":
            focusable.append(record)

    def order_label(record) -> str:
        text = _label_for(record) or record.attrs.get("placeholder") or record.tag
        return f"{clean_text(text)} ({record.tag})"

    has_focus_style = bool(re.search(r":focus(-visible)?\b", css or ""))
    empty_controls = [
        r
        for r in records
        if r.tag in {"a", "button"} and not _label_for(r) and not (r.tag == "a" and r.attrs.get("aria-label"))
    ]
    clickable_divs = [
        r for r in records if r.tag in {"div", "span"} and ("onclick" in r.attrs or r.attrs.get("role") == "button")
    ]
    positive_tabindex = [
        r for r in records if (r.attrs.get("tabindex") or "").lstrip("-").isdigit() and int(r.attrs["tabindex"]) > 0
    ]
    forms = [r for r in records if r.tag == "form"]
    submit_present = bool(
        re.search(
            r"<button\b[^>]*type=['\"]submit['\"]|<input\b[^>]*type=['\"]submit['\"]|<button\b(?![^>]*type=)",
            html or "",
            re.IGNORECASE,
        )
    )

    lines = [
        "KEYBOARD NAVIGATION TEST",
        "",
        f"I found {len(focusable)} keyboard-focusable element(s).",
    ]
    if focusable:
        lines.append("The likely tab order is:")
        lines.extend(f"{index}. {order_label(record)}" for index, record in enumerate(focusable[:12], start=1))
    else:
        lines.append("No focusable elements were found, so keyboard users have nothing to reach yet.")

    good: list[str] = []
    needs: list[str] = []
    if has_focus_style:
        good.append("The CSS includes a visible focus style.")
    else:
        needs.append("Add a visible :focus or :focus-visible style so keyboard users can see where they are.")
    if forms and not submit_present:
        needs.append("A form has no submit button; add a submit button so it can be completed by keyboard.")
    elif forms:
        good.append("Forms include a submit control.")
    for record in empty_controls[:3]:
        needs.append(f"A <{record.tag}> is empty; give it readable text or an aria-label.")
    for record in clickable_divs[:3]:
        needs.append(
            f"A <{record.tag}> looks clickable but is not a button or link; use a <button> so the keyboard can reach it."
        )
    if positive_tabindex:
        needs.append('Avoid positive tabindex values; they break the natural tab order. Use tabindex="0" or none.')

    if good:
        lines.append("")
        lines.append("Good:")
        lines.extend(f"- {item}" for item in good)
    if needs:
        lines.append("")
        lines.append("Needs work:")
        lines.extend(f"- {item}" for item in needs[:6])
    if not needs:
        lines.append("")
        lines.append("Everything focusable looks reachable by keyboard.")
    return "\n".join(lines).strip() + "\n"


_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_RGB = re.compile(r"rgba?\([^)]*\)")
_NAMED = (
    "white",
    "black",
    "navy",
    "teal",
    "coral",
    "lavender",
    "gold",
    "cream",
    "ink",
    "blue",
    "green",
    "red",
    "orange",
    "purple",
    "pink",
    "yellow",
    "gray",
    "grey",
)


def build_visual_description(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    records = parse_records(html)
    rules = parse_css_rules(css)
    selectors = " ".join(rule["selector"] for rule in rules).lower()
    declarations = " ".join(rule["declarations"] for rule in rules).lower()
    title = title_from_html(html, name or "this website")
    headings = [r for r in records if re.fullmatch(r"h[1-6]", r.tag)]
    sections = [r for r in records if r.tag in {"section", "article"}]
    has_forms = any(r.tag == "form" for r in records)

    uses_grid = "grid" in declarations or "display: grid" in declarations
    uses_flex = "flex" in declarations
    uses_cards = "card" in selectors
    uses_hero = "hero" in selectors

    layout = "a clean single-page layout"
    if uses_grid:
        layout = "a grid-based layout that arranges content into columns"
    elif uses_flex:
        layout = "a flexible layout that adapts as the window changes size"
    if uses_cards:
        layout += " with card-like sections"

    colors = set(_HEX.findall(css or "")) | set(_RGB.findall(css or ""))
    named = {word for word in _NAMED if re.search(rf"\b{word}\b", declarations)}
    palette_bits = sorted(named) or (["a custom color palette"] if colors else ["mostly default colors"])

    if len(colors) >= 6 or len(named) >= 4:
        tone = "colorful and lively"
    elif uses_cards or uses_hero:
        tone = "clean and professional"
    elif rules:
        tone = "simple and tidy"
    else:
        tone = "plain and lightly styled"

    lines = [
        "VISUAL DESCRIPTION",
        "",
        f"The website uses {layout}.",
    ]
    if uses_hero or headings:
        first = clean_text(headings[0].text) if headings else title
        lines.append(f"The top area acts like a hero section with a large heading: {first}.")
    if sections:
        lines.append(
            "Section order from top to bottom: " + ", ".join(clean_text(h.text, h.tag) for h in headings[:6]) + "."
        )
    lines.append(f"Color palette: {', '.join(palette_bits)}.")
    spacing = "generous spacing" if "gap" in declarations or "padding" in declarations else "compact spacing"
    lines.append(f"It uses {spacing} between elements.")
    pieces = []
    if any(r.tag == "button" for r in records):
        pieces.append("buttons")
    if uses_cards:
        pieces.append("cards")
    if has_forms:
        pieces.append("a form near the lower part of the page")
    if pieces:
        lines.append("Notable pieces: " + ", ".join(pieces) + ".")
    lines.append(f"Overall it feels {tone}.")
    lines.append(
        "A sighted visitor would probably notice the main title first, then the first button or call to action."
    )
    improvements = []
    if not uses_cards and sections:
        improvements.append("Group sections into cards for clearer separation.")
    if len(colors) < 2 and not named:
        improvements.append("Add one accent color to draw attention to the main action.")
    if improvements:
        lines.append("Possible visual improvements: " + " ".join(improvements))
    return "\n".join(lines).strip() + "\n"


def _readiness_metrics(html: str, css: str = "", js: str = "", audit: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute the readiness subscores, total, and the strong/needs/blocker lists.

    Shared by ``build_readiness_score`` (category breakdown text) and
    ``build_readiness_report`` (structured score/level/blockers/suggestions).
    """
    records = parse_records(html)
    headings = [r for r in records if re.fullmatch(r"h[1-6]", r.tag)]
    landmarks = [r for r in records if r.tag in {"header", "nav", "main", "section", "article", "footer", "form"}]
    has_main = any(r.tag == "main" for r in records)
    has_footer = any(r.tag == "footer" for r in records)
    rules = parse_css_rules(css)
    has_focus = bool(re.search(r":focus(-visible)?\b", css or ""))
    clickable_divs = [
        r for r in records if r.tag in {"div", "span"} and ("onclick" in r.attrs or r.attrs.get("role") == "button")
    ]
    focusable = [r for r in records if r.tag in FOCUSABLE_TAGS and not (r.tag == "a" and not r.attrs.get("href"))]
    audit_data = audit if isinstance(audit, dict) and "score" in audit else audit_html(html).to_dict()
    audit_score = int(audit_data.get("score") or 0)
    audit_issues = audit_data.get("issues") if isinstance(audit_data.get("issues"), list) else []
    debug_issues = collect_issues(html, css, js)
    # Richer, teacher-style findings (JS selector mismatches, duplicate ids, ...).
    from codeup.services.website_debugger import build_debug_teacher

    teacher_issues = build_debug_teacher(html, css, js)["issues"]
    has_files = bool((html or "").strip()) and bool((css or "").strip())

    # Subscores (weights sum to 100).
    structure = 15 if (len(headings) >= 2 and len(landmarks) >= 3) else 9 if headings else 3
    accessibility = round(audit_score / 100 * 25)
    visual = 12 if (rules and has_focus) else 8 if rules else 3
    keyboard = 15
    if not has_focus:
        keyboard -= 6
    if clickable_divs:
        keyboard -= 5
    if not focusable:
        keyboard -= 4
    keyboard = max(0, keyboard)
    content = 13 if (len(headings) >= 2 and has_main and has_footer) else 8 if has_main else 4
    code_quality = max(0, 12 - 3 * len(debug_issues))
    export_ready = 8 if has_files else 4
    total = structure + accessibility + visual + keyboard + content + code_quality + export_ready
    total = max(0, min(100, total))

    strong: list[str] = []
    needs: list[str] = []
    if structure >= 12:
        strong.append("Clear heading and landmark structure")
    else:
        needs.append("Add more headings and landmark sections")
    if accessibility >= 20:
        strong.append("Strong accessibility audit score")
    else:
        needs.append("Fix accessibility issues (try 'check accessibility' then 'fix accessibility issues')")
    if has_focus:
        strong.append("Visible keyboard focus style")
    else:
        needs.append("Add a visible focus style for keyboard users")
    if has_files:
        strong.append("Export files are ready")
    if clickable_divs:
        needs.append("Replace clickable divs with real buttons or links")
    if code_quality < 12:
        needs.append("Resolve the issues in 'debug this website'")
    if not strong:
        strong.append("The project has a clear starting point")
    if not needs:
        needs.append("Add a clearer footer and more specific button text")

    # Blockers: must-fix problems (high-severity accessibility + broken JS connections).
    blockers: list[str] = []
    for issue in audit_issues:
        if isinstance(issue, dict) and issue.get("severity") == "high":
            blockers.append(clean_text(str(issue.get("description") or issue.get("id") or "Accessibility issue")))
    for issue in teacher_issues:
        if issue.get("severity") == "high":
            blockers.append(clean_text(issue.get("spoken_summary") or issue.get("problem") or "Broken connection"))
    blockers = list(dict.fromkeys(blockers))[:6]

    if total >= 85:
        recommendation = "This is ready to share. Do a final read-through and export it."
    elif total >= 70:
        recommendation = "This is ready for a guided demo. I would fix the items above before sharing publicly."
    else:
        recommendation = "Keep improving the items above before sharing this widely."

    if blockers and total >= 85:
        level = "almost ready"
    elif total >= 85:
        level = "ready"
    elif total >= 70:
        level = "almost ready"
    else:
        level = "needs work"

    return {
        "structure": structure,
        "accessibility": accessibility,
        "visual": visual,
        "keyboard": keyboard,
        "content": content,
        "code_quality": code_quality,
        "export_ready": export_ready,
        "total": total,
        "strong": strong,
        "needs": needs,
        "blockers": blockers,
        "recommendation": recommendation,
        "level": level,
    }


def build_readiness_score(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> str:
    m = _readiness_metrics(html, css, js, audit)
    structure = m["structure"]
    accessibility = m["accessibility"]
    visual = m["visual"]
    keyboard = m["keyboard"]
    content = m["content"]
    code_quality = m["code_quality"]
    export_ready = m["export_ready"]
    total = m["total"]
    strong = m["strong"]
    needs = m["needs"]
    recommendation = m["recommendation"]

    lines = [
        f"WEBSITE READINESS SCORE: {total}/100",
        "",
        "Category breakdown:",
        f"- Structure: {structure}/15",
        f"- Accessibility: {accessibility}/25",
        f"- Visual clarity: {visual}/12",
        f"- Keyboard usability: {keyboard}/15",
        f"- Content completeness: {content}/13",
        f"- Beginner code quality: {code_quality}/12",
        f"- Export readiness: {export_ready}/8",
        "",
        "Strong:",
        *(f"- {item}" for item in strong[:5]),
        "",
        "Needs improvement:",
        *(f"- {item}" for item in needs[:5]),
        "",
        f"Recommendation:\n{recommendation}",
    ]
    return "\n".join(lines).strip() + "\n"


def build_readiness_report(
    html: str,
    css: str = "",
    js: str = "",
    *,
    name: str = "",
    project_type: str = "",
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured "ready to share?" check: score, level, blockers, suggestions.

    Combines the accessibility audit, structure/landmarks, keyboard risks, and
    JavaScript selector mismatches into one spoken-friendly readiness report.
    """
    if is_blank_project(html, css, js):
        text = "WEBSITE READINESS\n\n" + NO_PROJECT_MESSAGE + "\n"
        return {
            "score": 0,
            "level": "needs work",
            "text": text,
            "speech": NO_PROJECT_MESSAGE,
            "blockers": [],
            "suggestions": [],
        }

    m = _readiness_metrics(html, css, js, audit)
    total = m["total"]
    level = m["level"]
    blockers = m["blockers"]
    suggestions = list(dict.fromkeys(m["needs"]))[:6]

    level_phrase = {
        "ready": "This is ready to share.",
        "almost ready": "This is almost ready to share.",
        "needs work": "This still needs work before sharing.",
    }[level]

    lines = [
        "WEBSITE READINESS",
        "",
        f"Readiness score: {total} out of 100. {level_phrase}",
    ]
    if blockers:
        lines.append("")
        lines.append(f"Fix {'this' if len(blockers) == 1 else 'these'} first:")
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("I did not find any blockers.")
    if suggestions:
        lines.append("")
        lines.append("Then consider:")
        lines.extend(f"- {item}" for item in suggestions)
    lines.append("")
    lines.append(m["recommendation"])

    # Short spoken summary: score, level, and the first blocker (if any).
    if blockers:
        extra = "" if len(blockers) == 1 else f", and {len(blockers) - 1} more"
        speech = f"Readiness score {total} out of 100, {level}. Fix first: {blockers[0]}{extra}."
    else:
        speech = f"Readiness score {total} out of 100, {level}. I did not find any blockers."

    return {
        "score": total,
        "level": level,
        "text": "\n".join(lines).strip() + "\n",
        "speech": speech,
        "blockers": blockers,
        "suggestions": suggestions,
    }
