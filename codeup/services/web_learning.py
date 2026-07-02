from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from codeup.services.html_utils import audit_html, iter_nodes, parse_html


@dataclass
class TagRecord:
    tag: str
    attrs: dict[str, str]
    line: int
    depth: int
    text_parts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()

    @property
    def name(self) -> str:
        return self.attrs.get("aria-label") or self.attrs.get("alt") or self.text

    @property
    def selector(self) -> str:
        if self.attrs.get("id"):
            return f"#{self.attrs['id']}"
        classes = self.attrs.get("class", "").split()
        if classes:
            return f".{classes[0]}"
        return self.tag


class _StructureParser(HTMLParser):
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
        self.records: list[TagRecord] = []
        self.stack: list[TagRecord] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line, _column = self.getpos()
        record = TagRecord(
            tag=tag.lower(),
            attrs={name.lower(): value or "" for name, value in attrs},
            line=line,
            depth=len(self.stack),
        )
        self.records.append(record)
        if record.tag not in self.VOID_TAGS:
            self.stack.append(record)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == lowered:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if data.strip() and self.stack:
            self.stack[-1].text_parts.append(data.strip())


def parse_records(html: str) -> list[TagRecord]:
    parser = _StructureParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    return parser.records


TUTORIAL_MODULES: list[dict[str, Any]] = [
    {
        "id": "html_basics",
        "title": "HTML basics",
        "explanation": "HTML gives a web page its meaning. Start with a title, heading, and paragraph.",
        "command": "insert page title My First Website",
        "hint": "Then add a heading and paragraph, for example: insert heading Welcome and insert paragraph This is my first website.",
    },
    {
        "id": "structure",
        "title": "Sections and structure",
        "explanation": "Landmarks help screen reader users jump around the page.",
        "command": "insert header nav main section footer",
        "hint": "Use semantic regions: header, nav, main, section, and footer.",
    },
    {
        "id": "css_basics",
        "title": "CSS basics",
        "explanation": "CSS changes the look of the page without changing its meaning.",
        "command": "insert card styles",
        "hint": "Try commands that style the background, text, cards, or buttons.",
    },
    {
        "id": "javascript_basics",
        "title": "JavaScript basics",
        "explanation": "JavaScript adds behavior, such as a button that reacts when clicked.",
        "command": "add a button interaction",
        "hint": "The page needs a button and a click listener in script.js.",
    },
    {
        "id": "accessibility_repair",
        "title": "Accessibility repair",
        "explanation": "Accessibility repair checks names, labels, heading order, alt text, and contrast.",
        "command": "fix accessibility",
        "hint": "Run Analyze or Audit, then Fix Accessibility to repair safe issues.",
    },
    {
        "id": "export_share",
        "title": "Export and share",
        "explanation": "Preview checks the live website. Export creates files you can share.",
        "command": "run preview",
        "hint": "Run Preview first, then Export Project.",
    },
]


def tutorial_modules() -> list[dict[str, Any]]:
    return [dict(module) for module in TUTORIAL_MODULES]


def _has_text_node(html: str, tag: str) -> bool:
    root = parse_html(html)
    return any(node.text for node in iter_nodes(root, {tag}))


def validate_tutorial_step(module_id: str, html: str = "", css: str = "", js: str = "") -> dict[str, Any]:
    module = next((item for item in TUTORIAL_MODULES if item["id"] == module_id), None)
    if not module:
        return {
            "module": module_id,
            "valid": False,
            "message": "Unknown tutorial module.",
            "hint": "Start tutorial again.",
        }

    combined = (html or "") + "\n" + (css or "") + "\n" + (js or "")
    lowered = combined.lower()
    valid = False
    evidence: list[str] = []

    if module_id == "html_basics":
        valid = (
            _has_text_node(html, "title")
            and any(_has_text_node(html, tag) for tag in ("h1", "h2"))
            and _has_text_node(html, "p")
        )
        evidence = ["title", "heading", "paragraph"]
    elif module_id == "structure":
        tags = {record.tag for record in parse_records(html)}
        required = {"header", "nav", "main", "section", "footer"}
        valid = required <= tags
        evidence = sorted(required & tags)
    elif module_id == "css_basics":
        valid = bool(css.strip()) and any(
            token in lowered for token in ("background", "color", "button", "card", "border-radius")
        )
        evidence = ["CSS rules found"] if valid else []
    elif module_id == "javascript_basics":
        valid = "addeventlistener" in lowered and (
            "button" in lowered or "queryselector" in lowered or "getelementbyid" in lowered
        )
        evidence = ["button event listener"] if valid else []
    elif module_id == "accessibility_repair":
        audit = audit_html(html)
        blocking = {"missing_image_alt", "unnamed_button", "missing_form_label", "heading_skip"}
        remaining = [issue for issue in audit.issues if issue["id"] in blocking]
        valid = not remaining
        evidence = [f"accessibility score {audit.score}/100"]
    elif module_id == "export_share":
        valid = bool(html.strip()) and bool(css.strip() or js.strip())
        evidence = ["three-file project is ready"] if valid else []

    message = (
        f"Success. {module['title']} is complete. Evidence: {', '.join(evidence) or 'structure found'}."
        if valid
        else f"Not yet. {module['hint']}"
    )
    return {
        "module": module_id,
        "title": module["title"],
        "valid": valid,
        "message": message,
        "hint": module["hint"],
        "evidence": evidence,
    }


def _element_label(record: TagRecord) -> str:
    bits = [record.tag]
    if record.attrs.get("id"):
        bits.append(f"#{record.attrs['id']}")
    if record.attrs.get("class"):
        bits.append("." + ".".join(record.attrs["class"].split()[:2]))
    if record.name:
        bits.append(f'"{record.name[:48]}"')
    return " ".join(bits)


def _strip_css_comments(css: str) -> str:
    def replace(match: re.Match[str]) -> str:
        text = match.group(0)
        return "".join("\n" if char == "\n" else " " for char in text)

    return re.sub(r"/\*.*?\*/", replace, css or "", flags=re.DOTALL)


def parse_css_rules(css: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    clean_css = _strip_css_comments(css)
    for match in re.finditer(r"([^{}@][^{}]*)\{([^{}]*)\}", clean_css, flags=re.MULTILINE):
        selector_text = re.sub(r"\s+", " ", match.group(1)).strip()
        declarations = re.sub(r"\s+", " ", match.group(2)).strip()
        if not selector_text or ";" in selector_text:
            continue
        line = clean_css[: match.start()].count("\n") + 1
        for selector in [part.strip() for part in selector_text.split(",") if part.strip()]:
            props = [part.split(":", 1)[0].strip() for part in declarations.split(";") if ":" in part]
            rules.append({"selector": selector, "properties": props, "declarations": declarations, "line": line})
    return rules


def _last_selector_part(selector: str) -> str:
    parts = [part for part in re.split(r"\s+|[>+~]", selector.strip()) if part]
    return parts[-1] if parts else ""


def _selector_matches(selector: str, record: TagRecord) -> bool:
    if ":root" in selector and record.tag == "html":
        return True
    simple = _last_selector_part(selector)
    simple = re.sub(r":[\w-]+(?:\([^)]*\))?", "", simple)
    if not simple or simple == "*":
        return True
    attr_matches = re.findall(r"\[([a-zA-Z_:][\w:.-]*)(?:\s*[*^$|~]?=\s*['\"]?([^'\"\]]+)['\"]?)?\]", simple)
    simple = re.sub(r"\[[^\]]+\]", "", simple)

    ids = re.findall(r"#([\w-]+)", simple)
    if ids and any(record.attrs.get("id") != item for item in ids):
        return False
    classes = re.findall(r"\.([\w-]+)", simple)
    record_classes = record.attrs.get("class", "").split()
    if classes and not all(item in record_classes for item in classes):
        return False
    tag_match = re.match(r"^[a-zA-Z][\w-]*", simple)
    if tag_match and record.tag != tag_match.group(0).lower():
        return False

    if ids or classes or tag_match:
        return True
    if attr_matches:
        for attr, value in attr_matches:
            if attr == "data-theme" and record.tag == "html":
                continue
            actual = record.attrs.get(attr)
            if actual is None:
                return False
            if value and actual != value:
                return False
        return True
    if simple.startswith("#"):
        return record.attrs.get("id") == simple[1:]
    if simple.startswith("."):
        return simple[1:] in record.attrs.get("class", "").split()
    return False


def _selector_should_warn_when_unmatched(selector: str) -> bool:
    simple = _last_selector_part(selector)
    simple = re.sub(r":[\w-]+(?:\([^)]*\))?", "", simple)
    base = re.sub(r"\[[^\]]+\]", "", simple).strip()
    if not base or base in {"*", ":root"}:
        return False
    if "[" in simple and not re.search(r"[.#]", base):
        return False
    if re.fullmatch(r"[a-zA-Z][\w-]*", base):
        global_tags = {"html", "body", "main", "section", "article", "header", "footer", "a", "p", "img", "svg"}
        global_tags.update({f"h{level}" for level in range(1, 7)})
        return base.lower() not in global_tags
    return bool(re.search(r"[.#]", base))


def analyze_javascript(js: str) -> dict[str, Any]:
    functions = [
        {"name": name, "line": js[: match.start()].count("\n") + 1}
        for match in re.finditer(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", js or "")
        for name in [match.group(1)]
    ]
    functions.extend(
        {"name": match.group(1), "line": js[: match.start()].count("\n") + 1}
        for match in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", js or "")
    )
    listeners = [
        {"target": match.group(1).strip(), "event": match.group(2), "line": js[: match.start()].count("\n") + 1}
        for match in re.finditer(r"([A-Za-z_$][\w$.\]\[]+)\.addEventListener\(\s*['\"]([a-zA-Z]+)['\"]", js or "")
    ]
    queries = [
        {"method": "getElementById", "selector": f"#{match.group(1)}", "line": js[: match.start()].count("\n") + 1}
        for match in re.finditer(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", js or "")
    ]
    queries.extend(
        {"method": match.group(1), "selector": match.group(2), "line": js[: match.start()].count("\n") + 1}
        for match in re.finditer(r"(querySelector(?:All)?)\(\s*['\"]([^'\"]+)['\"]\s*\)", js or "")
    )
    return {"functions": functions, "listeners": listeners, "queries": queries}


def build_code_map(html: str, css: str = "", js: str = "", query: str = "") -> dict[str, Any]:
    records = parse_records(html)
    landmarks = [
        record
        for record in records
        if record.tag in {"header", "nav", "main", "section", "article", "aside", "footer", "form"}
    ]
    headings = [record for record in records if re.fullmatch(r"h[1-6]", record.tag)]
    buttons = [record for record in records if record.tag == "button"]
    links = [record for record in records if record.tag == "a"]
    forms = [record for record in records if record.tag == "form"]
    inputs = [record for record in records if record.tag in {"input", "textarea", "select"}]
    images = [record for record in records if record.tag == "img"]
    css_rules = parse_css_rules(css)
    js_map = analyze_javascript(js)

    for rule in css_rules:
        affects = [_element_label(record) for record in records if _selector_matches(rule["selector"], record)]
        rule["affects"] = affects[:8]

    lines = ["WEB CODE MAP", "", "HTML landmarks:"]
    lines.extend(
        f"- line {record.line}: {'  ' * record.depth}{record.tag}{' - ' + record.name if record.name else ''}"
        for record in landmarks
    )
    if not landmarks:
        lines.append("- none found")
    lines.append("")
    lines.append("Heading hierarchy:")
    lines.extend(
        f"- line {record.line}: {'  ' * (int(record.tag[1]) - 1)}{record.tag.upper()} {record.text}"
        for record in headings
    )
    if not headings:
        lines.append("- no headings found")
    lines.append("")
    lines.append("Controls and forms:")
    controls = buttons + links + forms + inputs
    lines.extend(f"- line {record.line}: {_element_label(record)}" for record in controls)
    if not controls:
        lines.append("- no buttons, links, or forms found")
    lines.append("")
    lines.append("Images:")
    lines.extend(
        f"- line {record.line}: image {'has alt text' if record.attrs.get('alt', '').strip() else 'is missing alt text'}"
        for record in images
    )
    if not images:
        lines.append("- no images found")
    lines.append("")
    lines.append("CSS selectors:")
    lines.extend(
        f"- line {rule['line']}: {rule['selector']} affects {', '.join(rule['affects']) if rule['affects'] else 'no obvious HTML element'}"
        for rule in css_rules[:20]
    )
    if not css_rules:
        lines.append("- no CSS rules found")
    lines.append("")
    lines.append("JavaScript:")
    lines.extend(f"- line {fn['line']}: function {fn['name']}()" for fn in js_map["functions"])
    lines.extend(
        f"- line {listener['line']}: {listener['target']} listens for {listener['event']}"
        for listener in js_map["listeners"]
    )
    lines.extend(f"- line {query_item['line']}: DOM query {query_item['selector']}" for query_item in js_map["queries"])
    if not js_map["functions"] and not js_map["listeners"] and not js_map["queries"]:
        lines.append("- no JavaScript behavior found")

    answer = answer_code_map_query(query, records, css_rules, js_map)
    if answer:
        lines = [answer, "", *lines]

    return {
        "summary": "\n".join(lines),
        "landmarks": [record.__dict__ | {"selector": record.selector, "name": record.name} for record in landmarks],
        "headings": [record.__dict__ | {"selector": record.selector, "name": record.name} for record in headings],
        "buttons": [record.__dict__ | {"selector": record.selector, "name": record.name} for record in buttons],
        "links": [record.__dict__ | {"selector": record.selector, "name": record.name} for record in links],
        "forms": [record.__dict__ | {"selector": record.selector, "name": record.name} for record in forms],
        "inputs": [record.__dict__ | {"selector": record.selector, "name": record.name} for record in inputs],
        "images": [
            record.__dict__
            | {"selector": record.selector, "name": record.name, "has_alt": bool(record.attrs.get("alt", "").strip())}
            for record in images
        ],
        "css": css_rules,
        "javascript": js_map,
        "answer": answer,
    }


def answer_code_map_query(
    query: str, records: list[TagRecord], css_rules: list[dict[str, Any]], js_map: dict[str, Any]
) -> str:
    lower = (query or "").lower()
    if not lower:
        return ""
    if "hero" in lower and "inside" in lower:
        hero = next(
            (
                record
                for record in records
                if "hero" in record.attrs.get("class", "") or record.attrs.get("id") == "hero"
            ),
            None,
        )
        if hero:
            nearby = [
                record
                for record in records
                if record.line >= hero.line and record.line <= hero.line + 20 and record.depth > hero.depth
            ]
            return "Inside the hero section: " + ", ".join(_element_label(record) for record in nearby[:8]) + "."
    if "after the navigation" in lower or "after navigation" in lower:
        nav = next((record for record in records if record.tag == "nav"), None)
        after = next(
            (
                record
                for record in records
                if nav and record.line > nav.line and record.tag in {"main", "section", "header", "footer"}
            ),
            None,
        )
        return (
            f"After the navigation comes line {after.line}: {_element_label(after)}."
            if after
            else "I could not find a landmark after the navigation."
        )
    if "list all buttons" in lower:
        buttons = [record for record in records if record.tag == "button"]
        return (
            "Buttons: "
            + (", ".join(f"line {record.line} {record.name or record.selector}" for record in buttons) or "none found")
            + "."
        )
    if "list all forms" in lower:
        forms = [record for record in records if record.tag == "form"]
        return (
            "Forms: "
            + (", ".join(f"line {record.line} {record.name or record.selector}" for record in forms) or "none found")
            + "."
        )
    if "css" in lower and "hero" in lower:
        matches = [rule for rule in css_rules if "hero" in rule["selector"]]
        return (
            "Hero CSS: "
            + (", ".join(f"line {rule['line']} {rule['selector']}" for rule in matches) or "no hero selector found")
            + "."
        )
    if "javascript" in lower and ("dark mode" in lower or "theme" in lower):
        matches = [
            item
            for item in js_map["queries"] + js_map["listeners"]
            if "theme" in str(item).lower() or "dark" in str(item).lower()
        ]
        return (
            "Dark mode JavaScript: "
            + (
                ", ".join(f"line {item['line']} {item.get('selector') or item.get('target')}" for item in matches)
                or "no obvious dark mode control found"
            )
            + "."
        )
    if "deeply nested" in lower:
        depth = max((record.depth for record in records), default=0)
        return f"The deepest HTML nesting level I found is {depth}."
    if "page structure" in lower:
        landmarks = [record.tag for record in records if record.tag in {"header", "nav", "main", "section", "footer"}]
        return "Page structure: " + (", ".join(landmarks) or "no landmarks found") + "."
    return ""


def watchpoint_pause(html: str, enabled: list[str] | None = None) -> dict[str, Any]:
    enabled_set = set(enabled or ["all"])
    audit = audit_html(html)
    groups = {
        "alt": {"missing_image_alt"},
        "image_alt": {"missing_image_alt"},
        "button_label": {"unnamed_button"},
        "form_label": {"missing_form_label"},
        "heading_order": {"heading_skip"},
        "contrast": {"low_contrast"},
        "accessibility": {issue["id"] for issue in audit.issues},
        "all": {issue["id"] for issue in audit.issues},
    }
    wanted = set()
    for key in enabled_set:
        wanted.update(groups.get(key, {key}))
    for issue in audit.issues:
        if issue["id"] in wanted:
            reason = f"Paused because {issue['description']} {issue['suggested_fix']}"
            return {"paused": True, "reason": reason, "issue": issue, "score": audit.score}
    return {
        "paused": False,
        "reason": "No watched accessibility issue is present.",
        "issue": None,
        "score": audit.score,
    }


def _line_diff(before: str, after: str, label: str) -> list[str]:
    changes = []
    diff = list(difflib.ndiff((before or "").splitlines(), (after or "").splitlines()))
    for line in diff:
        if line.startswith("+ "):
            changes.append(f"Added {label} line: {line[2:].strip()[:120]}")
        elif line.startswith("- "):
            changes.append(f"Removed {label} line: {line[2:].strip()[:120]}")
        if len(changes) >= 8:
            break
    return changes


def mistake_replay(
    html_before: str = "",
    html_after: str = "",
    css_before: str = "",
    css_after: str = "",
    js_before: str = "",
    js_after: str = "",
    mode: str = "summary",
) -> dict[str, Any]:
    from codeup.services.web_change_review import format_web_change_review, review_web_changes

    review = review_web_changes(
        html_before=html_before,
        html_after=html_after,
        css_before=css_before,
        css_after=css_after,
        js_before=js_before,
        js_after=js_after,
    )
    changes = [item["summary"] for item in review["files"]]
    if not changes:
        changes = ["No meaningful changes detected."]
    changes.append(f"Risk: {review['risk']}. {review['risk_reason']}")
    message = "Mistake replay:\n" + format_web_change_review(review, mode=mode)
    return {
        "message": message,
        "changes": changes[:16],
        "review": review,
        "changed_files": review["changed_files"],
        "risk": review["risk"],
        "risk_reason": review["risk_reason"],
    }


def explain_beginner_errors(html: str = "", css: str = "", js: str = "") -> dict[str, Any]:
    explanations = []
    stack: list[tuple[str, int]] = []
    voids = _StructureParser.VOID_TAGS
    for match in re.finditer(r"</?([a-zA-Z][\w-]*)(?:\s[^>]*)?>", html or ""):
        tag = match.group(1).lower()
        line = html[: match.start()].count("\n") + 1
        if match.group(0).startswith("</"):
            for index in range(len(stack) - 1, -1, -1):
                if stack[index][0] == tag:
                    del stack[index:]
                    break
        elif tag not in voids and not match.group(0).endswith("/>"):
            stack.append((tag, line))
    for tag, line in stack[-5:]:
        explanations.append(f"HTML line {line}: <{tag}> may be missing a closing </{tag}> tag.")

    if (css or "").count("{") != (css or "").count("}"):
        explanations.append("CSS has unbalanced braces. Every selector block needs an opening { and closing }.")

    records = parse_records(html)
    for rule in parse_css_rules(css):
        if not any(_selector_matches(rule["selector"], record) for record in records):
            if not _selector_should_warn_when_unmatched(rule["selector"]):
                continue
            explanations.append(
                f"CSS line {rule['line']}: selector {rule['selector']} does not match an obvious HTML element."
            )

    brackets = {"(": ")", "[": "]", "{": "}"}
    closers = {value: key for key, value in brackets.items()}
    js_stack: list[tuple[str, int]] = []
    for index, char in enumerate(js or ""):
        line = js[:index].count("\n") + 1
        if char in brackets:
            js_stack.append((char, line))
        elif char in closers:
            if not js_stack or js_stack[-1][0] != closers[char]:
                explanations.append(f"JavaScript line {line}: closing {char} does not match an opening bracket.")
                break
            js_stack.pop()
    if js_stack:
        opener, line = js_stack[-1]
        explanations.append(f"JavaScript line {line}: opening {opener} may not be closed.")

    for query in analyze_javascript(js)["queries"]:
        selector = query["selector"]
        if not any(_selector_matches(selector, record) for record in records):
            explanations.append(
                f"JavaScript line {query['line']}: DOM query {selector} does not match an element in the HTML."
            )

    for issue in audit_html(html).issues:
        if issue["id"] in {"missing_image_alt", "unnamed_button", "missing_form_label", "heading_skip", "low_contrast"}:
            explanations.append(f"Accessibility: {issue['description']} {issue['suggested_fix']}")

    if not explanations:
        explanations.append("I did not find a grounded HTML, CSS, JavaScript, or accessibility error.")
    return {
        "message": "Beginner explanation:\n" + "\n".join(f"- {item}" for item in explanations[:12]),
        "issues": explanations[:12],
    }
