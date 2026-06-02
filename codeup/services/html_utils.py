from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from typing import Any

from codeup.models import AuditResult


class HtmlNode:
    def __init__(self, tag: str, attrs: dict[str, str] | None = None, parent: HtmlNode | None = None) -> None:
        self.tag = tag.lower()
        self.attrs = attrs or {}
        self.parent = parent
        self.children: list[HtmlNode] = []
        self.text_parts: list[str] = []
        self.index = 0

    @property
    def text(self) -> str:
        chunks = list(self.text_parts)
        for child in self.children:
            chunks.append(child.text)
        return re.sub(r"\s+", " ", " ".join(chunks)).strip()

    def selector(self) -> str:
        if self.attrs.get("id"):
            return f"#{self.attrs['id']}"
        label = (self.attrs.get("aria-label") or self.attrs.get("alt") or self.text).strip()
        suffix = f"[{label[:32]}]" if label else f":nth-of-type({self.index})"
        return f"{self.tag}{suffix}"


class _TreeBuilder(HTMLParser):
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document")
        self.stack = [self.root]
        self.counts: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        clean_attrs = {name.lower(): value or "" for name, value in attrs}
        node = HtmlNode(tag, clean_attrs, self.stack[-1])
        self.counts[node.tag] = self.counts.get(node.tag, 0) + 1
        node.index = self.counts[node.tag]
        self.stack[-1].children.append(node)
        if node.tag not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == lowered:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].text_parts.append(data)


def parse_html(html: str) -> HtmlNode:
    parser = _TreeBuilder()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    return parser.root


def iter_nodes(root: HtmlNode, tags: set[str] | None = None) -> list[HtmlNode]:
    found = []

    def visit(node: HtmlNode) -> None:
        if tags is None or node.tag in tags:
            found.append(node)
        for child in node.children:
            visit(child)

    visit(root)
    return found


def first_node(root: HtmlNode, tag: str) -> HtmlNode | None:
    nodes = iter_nodes(root, {tag})
    return nodes[0] if nodes else None


def wrap_html(fragment: str) -> str:
    if "<html" in fragment.lower():
        return fragment
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>CodeUp Site</title></head>\n"
        f"<body>\n{fragment}\n</body>\n</html>"
    )


def extract_html(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidate = match.group(1).strip() if match else text.strip()
    lowered = candidate.lower()
    start = lowered.find("<!doctype html")
    if start == -1:
        start = lowered.find("<html")
    if start > 0:
        candidate = candidate[start:].strip()
    return wrap_html(candidate)


def html_text(html: str) -> str:
    root = parse_html(re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL))
    return root.text


def safe_page_filename(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name or "page").strip("-").lower()[:48]
    if slug in {"", "home", "index"}:
        return "index.html"
    return f"{slug}.html"


def is_safe_hosted_html_page(filename: str) -> bool:
    import os

    safe_name = os.path.basename(filename)
    return safe_name == filename and safe_name.endswith(".html") and safe_page_filename(safe_name[:-5]) == safe_name


def publish_page_plan(pages: dict[str, str]) -> tuple[list[tuple[str, str, str]], dict[str, list[str]]]:
    filenames: dict[str, list[str]] = {}
    plan: list[tuple[str, str, str]] = []
    for name, page_html in pages.items():
        filename = safe_page_filename(name)
        filenames.setdefault(filename, []).append(name)
        plan.append((name, filename, page_html))
    collisions = {filename: names for filename, names in filenames.items() if len(names) > 1}
    return plan, collisions


def title_from_prompt(prompt: str) -> str:
    cleaned = re.sub(r"(?i)\b(build|make|create|generate)\b", "", prompt)
    cleaned = re.sub(r"(?i)\b(a|an|the)?\s*(website|site|webpage|page)\s*(for|about)?\b", "", cleaned)
    words = [word.strip(" ,.-_") for word in cleaned.split() if word.strip(" ,.-_")]
    title = " ".join(words[:8]).strip() or "My CodeUp Website"
    return title.title()


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(hex_color: str) -> float:
        value = hex_color.strip().lstrip("#")
        if len(value) == 3:
            value = "".join(char * 2 for char in value)
        if len(value) != 6:
            return 0.0
        channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light = max(luminance(foreground), luminance(background))
    dark = min(luminance(foreground), luminance(background))
    return round((light + 0.05) / (dark + 0.05), 2)


def contrast_pairs(html: str) -> list[dict[str, Any]]:
    style_text = " ".join(re.findall(r"<style\b[^>]*>(.*?)</style>", html, flags=re.IGNORECASE | re.DOTALL))
    pairs = []
    blocks = re.findall(r"([^{}]+)\{([^{}]+)\}", style_text)
    variables = dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", style_text))

    def resolve(value: str) -> str:
        var_match = re.search(r"var\((--[\w-]+)\)", value)
        if var_match:
            return variables.get(var_match.group(1), "")
        color_match = re.search(r"#[0-9a-fA-F]{3,6}", value)
        return color_match.group(0) if color_match else ""

    for selector, declarations in blocks:
        color = ""
        background = ""
        for name, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", declarations):
            if name == "color":
                color = resolve(value)
            if name in {"background", "background-color"}:
                background = resolve(value)
        if color and background:
            ratio = contrast_ratio(color, background)
            pairs.append(
                {
                    "selector": re.sub(r"\s+", " ", selector).strip()[:80],
                    "foreground": color,
                    "background": background,
                    "ratio": ratio,
                    "passes_aa": ratio >= 4.5,
                }
            )
    if not pairs:
        pairs.append(
            {
                "selector": "body",
                "foreground": "#17202a",
                "background": "#ffffff",
                "ratio": contrast_ratio("#17202a", "#ffffff"),
                "passes_aa": True,
            }
        )
    return pairs[:12]


def screen_reader_checks(html: str) -> list[dict[str, Any]]:
    root = parse_html(html)
    headings = [int(node.tag[1]) for node in iter_nodes(root) if re.fullmatch(r"h[1-6]", node.tag)]
    skipped_heading = any(next_level - level > 1 for level, next_level in zip(headings, headings[1:], strict=False))
    controls = iter_nodes(root, {"button", "a", "input", "textarea", "select"})
    unnamed = 0
    for node in controls:
        if not accessible_name(node):
            unnamed += 1
    return [
        {
            "pattern": "NVDA heading navigation",
            "passed": bool(headings) and not skipped_heading,
            "note": "Headings exist and do not skip levels."
            if bool(headings) and not skipped_heading
            else "Add ordered headings so students can skim by heading.",
        },
        {
            "pattern": "JAWS landmark navigation",
            "passed": bool(iter_nodes(root, {"main", "nav", "header", "footer"})),
            "note": "Semantic landmarks are present.",
        },
        {
            "pattern": "VoiceOver control names",
            "passed": unnamed == 0,
            "note": "Interactive controls expose names."
            if unnamed == 0
            else f"{unnamed} controls may be announced without a useful name.",
        },
    ]


def screen_reader_transcript(html: str) -> list[dict[str, str]]:
    root = parse_html(html)
    role_names = {
        "header": "banner",
        "nav": "navigation",
        "main": "main",
        "footer": "content information",
        "section": "region",
        "article": "article",
        "form": "form",
        "a": "link",
        "button": "button",
        "img": "image",
        "input": "input",
        "textarea": "text area",
        "select": "menu",
    }
    transcript = []
    tags = {
        "header",
        "nav",
        "main",
        "footer",
        "section",
        "article",
        "form",
        "a",
        "button",
        "img",
        "input",
        "textarea",
        "select",
    }
    tags.update({f"h{level}" for level in range(1, 7)})
    for node in iter_nodes(root, tags):
        tag = node.tag
        name = accessible_name(node)
        if tag.startswith("h") and len(tag) == 2:
            role = f"heading level {tag[1]}"
            announcement = f"{role}, {name or 'unnamed'}"
        else:
            role = role_names.get(tag, tag)
            announcement = f"{role}, {name}" if name else f"{role}, unnamed"
        transcript.append({"tag": tag, "role": role, "name": name or "", "announcement": announcement[:220]})
        if len(transcript) >= 30:
            break
    if not transcript:
        transcript.append(
            {"tag": "document", "role": "document", "name": "", "announcement": "document, no readable body content"}
        )
    return transcript


def accessible_name(node: HtmlNode) -> str:
    for attr in ("aria-label", "alt", "placeholder", "title", "value"):
        if node.attrs.get(attr):
            return node.attrs[attr].strip()
    return node.text


def _issue(
    issue_id: str,
    severity: str,
    description: str,
    suggestion: str,
    selector: str = "document",
    autofix: bool = False,
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "severity": severity,
        "description": description,
        "selector": selector,
        "suggested_fix": suggestion,
        "autofix": autofix,
    }


def audit_html(html: str) -> AuditResult:
    root = parse_html(html)
    lowered = html.lower()
    html_node = first_node(root, "html")
    images = iter_nodes(root, {"img"})
    links = iter_nodes(root, {"a"})
    buttons = iter_nodes(root, {"button"})
    headings = [node for node in iter_nodes(root) if re.fullmatch(r"h[1-6]", node.tag)]
    labels = iter_nodes(root, {"label"})
    inputs = iter_nodes(root, {"input", "textarea", "select"})
    label_targets = {label.attrs.get("for", "") for label in labels if label.attrs.get("for")}
    landmark_nodes = iter_nodes(root, {"main", "section", "article", "header", "footer", "nav"})
    unlabeled_controls = []
    for control in inputs:
        if control.tag == "input" and control.attrs.get("type", "text").strip().lower() == "hidden":
            continue
        control_id = control.attrs.get("id", "")
        if accessible_name(control) or (control_id and control_id in label_targets):
            continue
        unlabeled_controls.append(control)
    form_label_ok = not unlabeled_controls
    checks = [
        ("Document starts with doctype", lowered.lstrip().startswith("<!doctype html")),
        ("Page has a language attribute", bool(html_node and html_node.attrs.get("lang"))),
        ("Page has a title", bool(first_node(root, "title") and first_node(root, "title").text)),
        ("Page has a viewport meta tag", 'name="viewport"' in lowered or "name='viewport'" in lowered),
        ("Page has an h1 heading", any(node.tag == "h1" for node in headings)),
        (
            "Images have alt text",
            all(bool(image.attrs.get("alt", "").strip()) for image in images),
        ),
        ("Buttons have readable labels", all(accessible_name(button) for button in buttons)),
        ("Links have readable labels", all(accessible_name(link) for link in links)),
        (
            "Uses semantic sections",
            bool(landmark_nodes),
        ),
        ("Form controls have labels", form_label_ok),
    ]
    passed = sum(1 for _, ok in checks if ok)
    issues = []
    if not lowered.lstrip().startswith("<!doctype html"):
        issues.append(
            _issue(
                "missing_doctype",
                "medium",
                "Document does not start with a doctype.",
                "Add <!doctype html> at the top.",
                autofix=True,
            )
        )
    if not (html_node and html_node.attrs.get("lang")):
        issues.append(
            _issue(
                "missing_lang",
                "high",
                "The html element has no language attribute.",
                'Add lang="en" to the html element.',
                "html",
                True,
            )
        )
    title = first_node(root, "title")
    if not (title and title.text):
        issues.append(
            _issue(
                "missing_title",
                "high",
                "The page has no readable title.",
                "Add a short title in the head.",
                "title",
                True,
            )
        )
    if 'name="viewport"' not in lowered and "name='viewport'" not in lowered:
        issues.append(
            _issue(
                "missing_viewport",
                "medium",
                "The page has no viewport meta tag.",
                "Add a responsive viewport meta tag.",
                "head",
                True,
            )
        )
    if not any(node.tag == "h1" for node in headings):
        issues.append(
            _issue("missing_h1", "high", "The page has no h1 heading.", "Add one h1 that names the page.", "body", True)
        )
    for image in images:
        if not image.attrs.get("alt", "").strip():
            issues.append(
                _issue(
                    "missing_image_alt",
                    "high",
                    "An image is missing alt text.",
                    "Add meaningful alt text.",
                    image.selector(),
                    True,
                )
            )
    for button in buttons:
        if not accessible_name(button):
            issues.append(
                _issue(
                    "unnamed_button",
                    "high",
                    "A button has no readable label.",
                    "Add visible text or an aria-label.",
                    button.selector(),
                    True,
                )
            )
    for link in links:
        if not accessible_name(link):
            issues.append(
                _issue(
                    "unnamed_link",
                    "high",
                    "A link has no readable label.",
                    "Add link text or an aria-label.",
                    link.selector(),
                    True,
                )
            )
    if not landmark_nodes:
        issues.append(
            _issue(
                "missing_landmarks",
                "medium",
                "The page does not use semantic landmark sections.",
                "Wrap body content in main and section landmarks.",
                "body",
                True,
            )
        )
    for control in unlabeled_controls:
        issues.append(
            _issue(
                "missing_form_label",
                "high",
                "A form control has no accessible label.",
                "Add a label or aria-label.",
                control.selector(),
                True,
            )
        )
    heading_levels = [int(node.tag[1]) for node in headings]
    if any(next_level - level > 1 for level, next_level in zip(heading_levels, heading_levels[1:], strict=False)):
        issues.append(
            _issue(
                "heading_skip",
                "medium",
                "Heading levels skip in a way that can confuse navigation.",
                "Use heading levels in order.",
                "headings",
                False,
            )
        )
    suggestions: list[str] = []
    if not headings:
        suggestions.append("Add headings so screen reader users can skim the page.")
    if any(issue["id"] == "missing_image_alt" for issue in issues):
        suggestions.append("Add meaningful alt text to every image.")
    if any(issue["id"] == "missing_landmarks" for issue in issues):
        suggestions.append("Use main, section, header, and footer landmarks.")
    if not suggestions:
        suggestions.append("Preview the page on mobile and ask a student to describe what they hear.")
    cp = contrast_pairs(html)
    src = screen_reader_checks(html)
    srt = screen_reader_transcript(html)
    if any(not pair["passes_aa"] for pair in cp):
        issues.append(
            _issue(
                "low_contrast",
                "high",
                "At least one text/background color pair misses WCAG AA contrast.",
                "Increase contrast to at least 4.5:1.",
                "style",
                False,
            )
        )
        suggestions.append("Increase text/background contrast until each normal text pair is at least 4.5:1.")
    if any(not check["passed"] for check in src):
        suggestions.append(
            "Run the page by headings, landmarks, and control names to match common screen reader navigation patterns."
        )
    return AuditResult(
        score=round((passed / len(checks)) * 100),
        passed=passed,
        total=len(checks),
        checks=[{"label": label, "passed": ok} for label, ok in checks],
        issues=issues,
        suggestions=suggestions,
        contrast_pairs=cp,
        screen_reader_checks=src,
        screen_reader_transcript=srt,
    )


def summarize_html_changes(before: str, after: str) -> list[str]:
    before_root = parse_html(before)
    after_root = parse_html(after)

    def counts(root: HtmlNode) -> dict[str, int]:
        tags = [node.tag for node in iter_nodes(root)]
        return {
            "headings": sum(1 for tag in tags if re.fullmatch(r"h[1-6]", tag)),
            "buttons": tags.count("button"),
            "links": tags.count("a"),
            "images": tags.count("img"),
            "forms": tags.count("form"),
            "landmarks": sum(1 for tag in tags if tag in {"main", "nav", "header", "footer", "section", "article"}),
        }

    before_counts = counts(before_root)
    after_counts = counts(after_root)
    summary = []
    for label, after_count in after_counts.items():
        before_count = before_counts[label]
        if after_count > before_count:
            summary.append(f"Added {after_count - before_count} {label}.")
        elif after_count < before_count:
            summary.append(f"Removed {before_count - after_count} {label}.")

    before_titles = {node.text for node in iter_nodes(before_root) if re.fullmatch(r"h[1-6]", node.tag)}
    after_titles = {node.text for node in iter_nodes(after_root) if re.fullmatch(r"h[1-6]", node.tag)}
    added_headings = sorted(title for title in after_titles - before_titles if title)
    removed_headings = sorted(title for title in before_titles - after_titles if title)
    if added_headings:
        summary.append("New headings: " + ", ".join(added_headings[:5]) + ".")
    if removed_headings:
        summary.append("Removed headings: " + ", ".join(removed_headings[:5]) + ".")
    return summary or ["No major structural changes detected."]


def _ensure_head_tag(html: str) -> str:
    document = wrap_html(html)
    if not re.search(r"<head\b", document, re.I):
        document = re.sub(r"(<html\b[^>]*>)", r"\1\n<head></head>", document, count=1, flags=re.I)
    return document


def _add_or_replace_lang(html: str) -> str:
    document = wrap_html(html)
    match = re.search(r"<html\b[^>]*>", document, re.I)
    if not match:
        return document

    tag = match.group(0)
    lang_match = re.search(r'\blang\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]*)', tag, re.I)
    if lang_match:
        value = lang_match.group(1).strip("\"'")
        if value.strip():
            return document
        replacement = tag[: lang_match.start()] + 'lang="en"' + tag[lang_match.end() :]
    else:
        replacement = tag[:-1].rstrip() + ' lang="en">'
    return document[: match.start()] + replacement + document[match.end() :]


def _add_or_replace_title(html: str) -> str:
    document = _ensure_head_tag(html)
    title_match = re.search(r"<title\b[^>]*>(.*?)</title\s*>", document, re.I | re.S)
    if not title_match:
        return _insert_head_child(document, "<title>CodeUp Project</title>")
    if title_match.group(1).strip():
        return document
    replacement = "<title>CodeUp Project</title>"
    return document[: title_match.start()] + replacement + document[title_match.end() :]


def _insert_head_child(html: str, markup: str) -> str:
    document = _ensure_head_tag(html)
    return re.sub(r"</head\s*>", f"{markup}\n</head>", document, count=1, flags=re.I)


def _missing_form_label_targets(html: str) -> set[str]:
    root = parse_html(html)
    labels = iter_nodes(root, {"label"})
    label_targets = {label.attrs.get("for", "") for label in labels if label.attrs.get("for")}
    targets: set[str] = set()
    for control in iter_nodes(root, {"input", "textarea", "select"}):
        if control.tag == "input" and control.attrs.get("type", "text").strip().lower() == "hidden":
            continue
        control_id = control.attrs.get("id", "")
        if accessible_name(control) or (control_id and control_id in label_targets):
            continue
        targets.add(control.selector())
    return targets


def _add_or_replace_aria_label(tag: str, label: str = "Input field") -> str:
    aria_match = re.search(r'\baria-label\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]*)', tag, re.I)
    if aria_match:
        value = aria_match.group(1).strip("\"'")
        if value.strip():
            return tag
        return tag[: aria_match.start()] + f'aria-label="{label}"' + tag[aria_match.end() :]
    return re.sub(r"^<([a-zA-Z][\w:-]*)\b", rf'<\1 aria-label="{label}"', tag, count=1)


def _tag_attr(tag: str, name: str) -> str:
    match = re.search(rf'\b{name}\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]*)', tag, re.I)
    return match.group(1).strip("\"'") if match else ""


def _tag_selector(tag_name: str, tag: str, index: int) -> str:
    tag_id = _tag_attr(tag, "id")
    if tag_id:
        return f"#{tag_id}"
    return f"{tag_name}:nth-of-type({index})"


def _tag_selector_matches(tag_name: str, tag: str, index: int, selector: str | None) -> bool:
    if not selector:
        return True
    if selector.startswith("#"):
        return _tag_attr(tag, "id") == selector[1:]
    match = re.fullmatch(rf"{re.escape(tag_name)}:nth-of-type\((\d+)\)", selector)
    return bool(match and index == int(match.group(1)))


def apply_audit_fixes(
    html: str, issue_id: str | None = None, fix_all: bool = False, issue_selector: str | None = None
) -> tuple[str, list[str], AuditResult]:
    audit = audit_html(html)
    selected = [issue for issue in audit.issues if issue.get("autofix")]
    if issue_id:
        selected = [issue for issue in selected if issue["id"] == issue_id]
    elif not fix_all:
        selected = selected[:1]
    selected_ids = {issue["id"] for issue in selected}
    updated = html
    fixed: list[str] = []

    if "missing_doctype" in selected_ids and not updated.lstrip().lower().startswith("<!doctype html"):
        updated = "<!doctype html>\n" + updated.lstrip()
        fixed.append("missing_doctype")
    if "missing_lang" in selected_ids:
        previous = updated
        updated = _add_or_replace_lang(updated)
        if updated != previous:
            fixed.append("missing_lang")
    if "missing_title" in selected_ids and not (
        first_node(parse_html(updated), "title") and first_node(parse_html(updated), "title").text
    ):
        previous = updated
        updated = _add_or_replace_title(updated)
        if updated != previous:
            fixed.append("missing_title")
    if (
        "missing_viewport" in selected_ids
        and 'name="viewport"' not in updated.lower()
        and "name='viewport'" not in updated.lower()
    ):
        updated = _insert_head_child(updated, '<meta name="viewport" content="width=device-width, initial-scale=1">')
        fixed.append("missing_viewport")
    if "missing_h1" in selected_ids and not any(node.tag == "h1" for node in iter_nodes(parse_html(updated))):
        if re.search(r"<body\b[^>]*>", updated, re.I):
            updated = re.sub(r"(<body\b[^>]*>)", r"\1\n<h1>Untitled Page</h1>", updated, count=1, flags=re.I)
        else:
            updated = f"<h1>Untitled Page</h1>\n{updated}"
        fixed.append("missing_h1")
    if "missing_image_alt" in selected_ids:
        img_count = 0

        def add_alt(match: re.Match[str]) -> str:
            nonlocal img_count
            img_count += 1
            tag = match.group(0)
            if not _tag_selector_matches("img", tag, img_count, issue_selector):
                return tag
            alt_match = re.search(r'\balt\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]*)', tag, re.I)
            if alt_match:
                value = alt_match.group(1).strip("\"'")
                if value.strip():
                    return tag
                return tag[: alt_match.start()] + 'alt="Describe this image"' + tag[alt_match.end() :]
            if re.search(r"\balt\s*=", tag, re.I):
                return tag
            return tag[:-1].rstrip(" /") + ' alt="Describe this image">'

        previous = updated
        updated = re.sub(r"<img\b[^>]*>", add_alt, updated, flags=re.I)
        if updated != previous:
            fixed.append("missing_image_alt")
    if "unnamed_button" in selected_ids:
        button_count = 0

        def label_button(match: re.Match[str]) -> str:
            nonlocal button_count
            button_count += 1
            opening = match.group(1)
            text = match.group(2)
            tag = f"<button{opening}>"
            if not _tag_selector_matches("button", tag, button_count, issue_selector) or text.strip():
                return match.group(0)
            return f"<button{opening}>Button</button>"

        previous = updated
        updated = re.sub(r"<button\b([^>]*)>(.*?)</button>", label_button, updated, flags=re.I | re.S)
        if updated != previous:
            fixed.append("unnamed_button")
    if "unnamed_link" in selected_ids:
        link_count = 0

        def label_link(match: re.Match[str]) -> str:
            nonlocal link_count
            link_count += 1
            opening = match.group(1)
            text = match.group(2)
            tag = f"<a{opening}>"
            if not _tag_selector_matches("a", tag, link_count, issue_selector) or text.strip():
                return match.group(0)
            return f'<a{opening} aria-label="Link">Link</a>'

        previous = updated
        updated = re.sub(r"<a\b([^>]*)>(.*?)</a>", label_link, updated, flags=re.I | re.S)
        if updated != previous:
            fixed.append("unnamed_link")
    if "missing_landmarks" in selected_ids and not iter_nodes(
        parse_html(updated), {"main", "section", "article", "header", "footer", "nav"}
    ):
        if re.search(r"<body\b[^>]*>", updated, re.I):
            updated = re.sub(r"(<body\b[^>]*>)", r"\1\n<main>", updated, count=1, flags=re.I)
            updated = re.sub(r"</body\s*>", r"</main>\n</body>", updated, count=1, flags=re.I)
        else:
            updated = f"<main>\n{updated}\n</main>"
        fixed.append("missing_landmarks")
    if "missing_form_label" in selected_ids:
        targets = _missing_form_label_targets(updated)
        if issue_selector:
            targets = {target for target in targets if target == issue_selector}
        counts: dict[str, int] = {}

        def label_control(match: re.Match[str]) -> str:
            tag_name = match.group(1).lower()
            counts[tag_name] = counts.get(tag_name, 0) + 1
            selector = _tag_selector(tag_name, match.group(0), counts[tag_name])
            if selector not in targets:
                return match.group(0)
            return _add_or_replace_aria_label(match.group(0))

        previous = updated
        updated = re.sub(r"<(input|textarea|select)\b[^>]*>", label_control, updated, flags=re.I)
        if updated != previous:
            fixed.append("missing_form_label")

    return updated, sorted(set(fixed)), audit_html(updated)


def fallback_site(prompt: str) -> str:
    title = title_from_prompt(prompt)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "codeup-site"
    safe_title = escape(title)
    safe_prompt = escape(prompt)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #13231f;
      --muted: #4f635f;
      --paper: #fbf8f2;
      --panel: #ffffff;
      --brand: #0f766e;
      --accent: #f59e0b;
      --line: #d7e1dc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      color: var(--ink);
      background: var(--paper);
      line-height: 1.6;
    }}
    header {{
      padding: 48px 20px;
      background: #0f766e;
      color: white;
      text-align: center;
    }}
    header h1 {{ margin: 0 0 10px; font-size: clamp(2rem, 6vw, 4rem); }}
    header p {{ max-width: 680px; margin: 0 auto; font-size: 1.1rem; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 28px 18px 44px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      margin: 18px 0;
    }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    .card {{ border-left: 5px solid var(--accent); }}
    a.button {{
      display: inline-block;
      margin-top: 8px;
      padding: 10px 14px;
      border-radius: 6px;
      color: #10201d;
      background: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }}
    footer {{ padding: 22px; text-align: center; color: var(--muted); }}
  </style>
</head>
<body>
  <header>
    <h1>{safe_title}</h1>
    <p>A clear, accessible website made in CodeUp HTML for the request: {safe_prompt}.</p>
  </header>
  <main id="{slug}">
    <section aria-labelledby="about-heading">
      <h2 id="about-heading">About This Website</h2>
      <p>This page introduces the topic, gives visitors the main details, and keeps the structure easy to understand with headings and short sections.</p>
    </section>
    <section aria-labelledby="highlights-heading">
      <h2 id="highlights-heading">Highlights</h2>
      <div class="grid">
        <article class="card"><h3>Clear Purpose</h3><p>Visitors can quickly understand what the website is for.</p></article>
        <article class="card"><h3>Accessible Layout</h3><p>Semantic headings, strong contrast, and responsive spacing support screen readers and mobile devices.</p></article>
        <article class="card"><h3>Easy Next Step</h3><p>The call to action tells visitors what they can do next.</p></article>
      </div>
    </section>
    <section aria-labelledby="action-heading">
      <h2 id="action-heading">Get Involved</h2>
      <p>Add your real details here: timings, contact information, photos with alt text, or links.</p>
      <a class="button" href="#about-heading">Back to top</a>
    </section>
  </main>
  <footer>Built locally with CodeUp HTML.</footer>
</body>
</html>"""
