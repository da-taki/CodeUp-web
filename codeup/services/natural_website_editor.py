from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from codeup.config import MAX_HTML_SIZE
from codeup.services.ai_service import call_ai, is_ai_unavailable
from codeup.services.html_utils import audit_html, wrap_html

ALLOWED_EDIT_ACTIONS = frozenset({"update_website", "ask_clarification", "refuse_unsafe"})
SECURITY_PATTERNS = (
    (re.compile(r"<script\b[^>]*\bsrc\s*=\s*['\"]?https?://", re.I), "External script URLs are not allowed."),
    (
        re.compile(r"<script\b[^>]*(?:gtag|google-analytics|analytics|facebook\.net|tracking|pixel)", re.I),
        "Tracking code is not allowed.",
    ),
    (re.compile(r"\b(?:gtag|fbq)\s*\(", re.I), "Tracking code is not allowed."),
    (re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(", re.I), "Dynamic JavaScript execution is not allowed."),
    (re.compile(r"\bdocument\.cookie\b", re.I), "Cookie access is not allowed."),
    (
        re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket)\s*\(", re.I),
        "Network calls are not allowed in student websites.",
    ),
    (re.compile(r"\bwindow\.location\s*=", re.I), "Automatic redirects are not allowed."),
    (re.compile(r"\bon[a-z]+\s*=", re.I), "Inline JavaScript event handlers are not allowed."),
    (
        re.compile(r"\b(?:api[_-]?key|secret|token)\b\s*[:=]\s*['\"][A-Za-z0-9_.-]{12,}", re.I),
        "Secrets or API keys are not allowed.",
    ),
    (
        re.compile(r"\b(?:password|credit card|card number|cvv|bank login|social security|ssn)\b", re.I),
        "Credential or payment collection is not allowed.",
    ),
    (re.compile(r"\bhref\s*=\s*['\"]\s*javascript:", re.I), "javascript: links are not allowed."),
    (
        re.compile(r"<a\b[^>]*(?:hidden|display\s*:\s*none|visibility\s*:\s*hidden)[^>]*https?://", re.I),
        "Hidden external links are not allowed.",
    ),
)


@dataclass
class WebsiteValidation:
    valid: bool
    files: dict[str, str]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class EditPlan:
    action: str
    confidence: float
    files: dict[str, str]
    summary: str
    needs_clarification: bool = False
    clarification_question: str = ""
    safety_notes: list[str] = field(default_factory=list)
    validation: WebsiteValidation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "files": self.files,
            "summary": self.summary,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "safety_notes": self.safety_notes,
            "validation": self.validation.to_dict() if self.validation else {},
        }


def _normalize_files(files: dict[str, Any] | None) -> dict[str, str]:
    files = files or {}
    return {
        "index.html": str(files.get("index.html") or files.get("html") or ""),
        "style.css": str(files.get("style.css") or files.get("styles.css") or files.get("css") or ""),
        "script.js": str(files.get("script.js") or files.get("js") or ""),
    }


def _has_markdown_fence(value: str) -> bool:
    return "```" in (value or "")


def _semantic_warnings(html: str, css: str) -> list[str]:
    warnings: list[str] = []
    audit = audit_html(html)
    for issue in audit.issues:
        if issue["id"] == "low_contrast":
            warnings.append(issue["description"])
    if ":focus" not in css and ":focus-visible" not in css:
        warnings.append("No custom keyboard focus style was found in CSS.")
    if len(re.findall(r"<div\b", html, re.I)) >= 5 and not re.search(
        r"<(main|section|article|nav|header|footer)\b", html, re.I
    ):
        warnings.append("The page appears to rely on divs instead of semantic landmarks.")
    return warnings


def validate_website_files(files: dict[str, Any] | None) -> WebsiteValidation:
    normalized = _normalize_files(files)
    html = normalized["index.html"].strip()
    css = normalized["style.css"].strip()
    js = normalized["script.js"].strip()
    errors: list[str] = []
    warnings: list[str] = []

    if not html:
        errors.append("index.html is missing.")
    if len(html) > MAX_HTML_SIZE or len(css) > MAX_HTML_SIZE or len(js) > MAX_HTML_SIZE:
        errors.append(f"One or more files are too large. Each file must stay under {MAX_HTML_SIZE} bytes.")
    for filename, content in normalized.items():
        if _has_markdown_fence(content):
            errors.append(f"{filename} contains markdown fences.")
        for pattern, message in SECURITY_PATTERNS:
            if pattern.search(content):
                errors.append(f"{filename}: {message}")

    if html and not re.search(r"<html\b", html, re.I):
        html = wrap_html(html)
        normalized["index.html"] = html
        warnings.append("Wrapped the HTML fragment in a complete document.")

    if html:
        audit = audit_html(html)
        blocking_ids = {"missing_title", "missing_h1", "missing_lang", "missing_form_label", "missing_image_alt"}
        blocking = [issue for issue in audit.issues if issue["id"] in blocking_ids]
        for issue in blocking:
            errors.append(f"{issue['id']}: {issue['description']}")
        warnings.extend(_semantic_warnings(html, css))

    return WebsiteValidation(valid=not errors, files=normalized, errors=errors, warnings=sorted(set(warnings)))


def _extract_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if match:
        text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _replace_title_and_h1(html: str, title: str) -> str:
    safe = _escape_text(title) or "CodeUp Web"
    document = wrap_html(html)
    if re.search(r"<title\b[^>]*>.*?</title\s*>", document, re.I | re.S):
        document = re.sub(
            r"<title\b[^>]*>.*?</title\s*>", f"<title>{safe}</title>", document, count=1, flags=re.I | re.S
        )
    else:
        document = re.sub(r"</head\s*>", f"<title>{safe}</title>\n</head>", document, count=1, flags=re.I)
    if re.search(r"<h1\b[^>]*>.*?</h1\s*>", document, re.I | re.S):
        document = re.sub(
            r"(<h1\b[^>]*>).*?(</h1\s*>)",
            lambda match: f"{match.group(1)}{safe}{match.group(2)}",
            document,
            count=1,
            flags=re.I | re.S,
        )
    return document


def _escape_text(value: str) -> str:
    return (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").strip()


def _insert_before_footer_or_body(html: str, block: str) -> str:
    document = wrap_html(html)
    if re.search(r"<footer\b", document, re.I):
        return re.sub(r"\s*<footer\b", "\n" + block.strip() + "\n<footer", document, count=1, flags=re.I)
    if re.search(r"</main\s*>", document, re.I):
        return re.sub(r"</main\s*>", block.strip() + "\n</main>", document, count=1, flags=re.I)
    return re.sub(r"</body\s*>", block.strip() + "\n</body>", document, count=1, flags=re.I)


def _section_block(topic: str) -> str:
    label = _escape_text(topic.title() if topic else "About")
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "new-section"
    return f"""
<section id="{slug}" aria-labelledby="{slug}-heading">
  <h2 id="{slug}-heading">{label}</h2>
  <p>This section explains {label.lower()} in simple, welcoming language for every visitor.</p>
</section>
"""


def _contact_block() -> str:
    return """
<section id="contact" aria-labelledby="contact-heading">
  <h2 id="contact-heading">Contact Us</h2>
  <p>Send a question or ask how to get involved.</p>
  <form data-contact-form novalidate>
    <label for="contact-name">Your name</label>
    <input id="contact-name" name="name" type="text" autocomplete="name" required>
    <label for="contact-email">Email address</label>
    <input id="contact-email" name="email" type="email" autocomplete="email" required>
    <label for="contact-message">Message</label>
    <textarea id="contact-message" name="message" rows="4" required></textarea>
    <button type="submit">Send message</button>
    <p class="form-status" aria-live="polite" data-form-status></p>
  </form>
</section>
"""


def _footer_block() -> str:
    return """
<footer class="site-footer">
  <p>Made with CodeUp Web. This page is designed to be readable, keyboard friendly, and accessible.</p>
</footer>
"""


def _shorten_title(html: str) -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1\s*>", html, re.I | re.S)
    if not match:
        return html
    text = re.sub(r"<[^>]+>", " ", match.group(1))
    words = re.sub(r"\s+", " ", text).strip().split()
    shortened = " ".join(words[:5]).strip() or "Welcome"
    if len(words) > 5:
        return _replace_title_and_h1(html, shortened)
    return html


def _professional_css() -> str:
    return """

:root { --surface: #ffffff; --ink: #17202a; --muted: #526070; --brand: #1f6f8b; --accent: #f59e0b; }
body { color: var(--ink); background: #f7fafc; line-height: 1.65; }
header, .hero { background: linear-gradient(135deg, #1f6f8b, #2f855a); color: #ffffff; }
main section, article, .card { background: var(--surface); border: 1px solid #d8e2ea; border-radius: 8px; }
a, button, .button { font-weight: 700; }
a:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible { outline: 3px solid #f59e0b; outline-offset: 3px; }
"""


def _color_css(color: str = "blue") -> str:
    palettes = {
        "blue": ("#1d4ed8", "#0f766e"),
        "green": ("#047857", "#1d4ed8"),
        "purple": ("#6d28d9", "#0f766e"),
        "red": ("#b91c1c", "#1d4ed8"),
        "orange": ("#c2410c", "#0f766e"),
    }
    brand, accent = palettes.get(color, ("#1d4ed8", "#0f766e"))
    return f"""

:root {{ --brand: {brand}; --accent: {accent}; }}
header, .hero {{ background: linear-gradient(135deg, var(--brand), var(--accent)); color: #ffffff; }}
a, button, .button {{ color: #ffffff; background: var(--brand); }}
a:focus-visible, button:focus-visible {{ outline: 3px solid #f59e0b; outline-offset: 3px; }}
"""


def _simple_css() -> str:
    return """

body { font-size: 1.05rem; line-height: 1.75; }
main { max-width: 980px; margin: 0 auto; }
section, article, .card { padding: 1.25rem; }
p, li { max-width: 70ch; }
"""


def _ensure_nav(html: str) -> str:
    if re.search(r"<nav\b", html, re.I):
        return html
    nav = """
<nav aria-label="Main navigation">
  <a href="#about">About</a>
  <a href="#contact">Contact</a>
</nav>
"""
    if re.search(r"</header\s*>", html, re.I):
        return re.sub(r"</header\s*>", nav.strip() + "\n</header>", html, count=1, flags=re.I)
    return re.sub(
        r"<body\b[^>]*>", lambda match: match.group(0) + "\n" + nav.strip(), wrap_html(html), count=1, flags=re.I
    )


def _remove_section_by_phrase(html: str, phrase: str) -> str:
    lowered_phrase = re.escape(phrase.lower())
    pattern = re.compile(r"\s*<section\b[^>]*>.*?" + lowered_phrase + r".*?</section\s*>\s*", re.I | re.S)
    return pattern.sub("\n", html, count=1)


def _deterministic_plan(files: dict[str, str], instruction: str) -> EditPlan:
    current = _normalize_files(files)
    html = current["index.html"]
    css = current["style.css"]
    js = current["script.js"]
    lower = instruction.lower()
    changes: list[str] = []

    rename = re.search(
        r"\b(?:change|rename|set)\s+(?:the\s+)?(?:website\s+)?(?:name|title)\s+to\s+(.+)$", instruction, re.I
    )
    if rename:
        html = _replace_title_and_h1(html, rename.group(1).strip(" ."))
        changes.append(f"Changed the website name to {rename.group(1).strip(' .')}.")

    if "title shorter" in lower or "shorter title" in lower or "make the title short" in lower:
        updated = _shorten_title(html)
        if updated != html:
            html = updated
            changes.append("Shortened the page title and main heading.")

    remove_match = re.search(r"\bremove\s+(?:the\s+)?(.+?)\s+section\b", instruction, re.I)
    if remove_match:
        phrase = remove_match.group(1).strip()
        updated = _remove_section_by_phrase(html, phrase)
        if updated != html:
            html = updated
            changes.append(f"Removed the {phrase} section.")

    section_match = re.search(
        r"\badd\s+(?:an?\s+)?(?:section\s+)?(?:about\s+)?(.+?)(?:\s+section)?$", instruction, re.I
    )
    if section_match and "contact" not in lower and "footer" not in lower and "navigation" not in lower:
        topic = section_match.group(1).strip(" .") or "about"
        if topic in {"an", "a", "section"}:
            topic = "about"
        html = _insert_before_footer_or_body(html, _section_block(topic))
        changes.append(f"Added a {topic} section.")
    elif "add an about section" in lower or "add about section" in lower:
        html = _insert_before_footer_or_body(html, _section_block("about"))
        changes.append("Added an About section.")

    if "contact form" in lower or ("contact" in lower and "section" in lower):
        if "data-contact-form" not in html and 'id="contact"' not in html:
            html = _insert_before_footer_or_body(html, _contact_block())
            changes.append("Added an accessible contact form.")

    if "add footer" in lower or "footer" in lower and "clearer" in lower:
        if not re.search(r"<footer\b", html, re.I):
            html = re.sub(r"</body\s*>", _footer_block().strip() + "\n</body>", wrap_html(html), count=1, flags=re.I)
            changes.append("Added a footer.")

    if "navigation" in lower or "nav" in lower:
        html = _ensure_nav(html)
        changes.append("Improved the navigation structure.")

    color_match = re.search(r"\b(?:theme|color|colour)\s+to\s+(blue|green|purple|red|orange)\b", lower)
    if color_match:
        css += _color_css(color_match.group(1))
        changes.append(f"Changed the theme to {color_match.group(1)}.")
    elif "more colorful" in lower or "more colourful" in lower:
        css += _color_css("blue")
        changes.append("Made the theme more colorful with accessible contrast.")

    if "professional" in lower:
        css += _professional_css()
        changes.append("Made the visual style more professional.")
    if "simpler" in lower or "easier to read" in lower or "text easier" in lower:
        css += _simple_css()
        changes.append("Made the page easier to read.")
    if "button" in lower and ("clearer" in lower or "clear" in lower):
        css += "\nbutton, .button, a.button { min-height: 44px; padding: 0.75rem 1rem; border-radius: 8px; }\n"
        changes.append("Made buttons larger and clearer.")

    if "score tracking" in lower or "track score" in lower:
        if "quiz-score" in html or "quizScore" in js or "score" in js.lower():
            changes.append("Score tracking is already present in the quiz app.")
        else:
            html = _insert_before_footer_or_body(
                html,
                """
<section id="score-tracking" aria-labelledby="score-tracking-heading">
  <h2 id="score-tracking-heading">Score Tracking</h2>
  <p class="status" id="quiz-score" aria-live="polite">Score: 0</p>
</section>
""",
            )
            js += """

var quizScoreStatus = document.getElementById("quiz-score");
if (quizScoreStatus) {
  quizScoreStatus.textContent = "Score tracking is ready.";
}
"""
            changes.append("Added a score tracking status area.")

    if not changes:
        return EditPlan(
            action="ask_clarification",
            confidence=0.3,
            files=current,
            summary="I need a clearer edit request.",
            needs_clarification=True,
            clarification_question="What part of the website should I change?",
        )

    updated_files = {"index.html": html, "style.css": css, "script.js": js}
    validation = validate_website_files(updated_files)
    if not validation.valid:
        return EditPlan(
            action="refuse_unsafe",
            confidence=0.8,
            files=current,
            summary="The edit was not applied because validation failed.",
            safety_notes=validation.errors,
            validation=validation,
        )
    return EditPlan(
        action="update_website",
        confidence=0.82,
        files=validation.files,
        summary=" ".join(changes),
        safety_notes=validation.warnings,
        validation=validation,
    )


def _ai_plan(
    files: dict[str, str], metadata: dict[str, Any], instruction: str, language: str = "en"
) -> EditPlan | None:
    system = """You are the edit planner for CodeUp Web, an accessibility-first website builder.
Return strict JSON only. No markdown fences.
Schema:
{
  "action": "update_website|ask_clarification|refuse_unsafe",
  "confidence": 0.0,
  "files": {
    "index.html": "...",
    "style.css": "...",
    "script.js": "..."
  },
  "summary": "Short beginner-friendly summary.",
  "needs_clarification": false,
  "clarification_question": "",
  "safety_notes": []
}
Rules:
- Preserve the current website topic and useful content.
- Apply the user's edit to the existing files; do not replace the project with an unrelated site.
- Keep semantic HTML, title, h1, labels, alt text, landmarks, focus styles, readable contrast, and responsive CSS.
- Do not use external scripts, trackers, credential collection, network calls, markdown fences, or secrets.
"""
    current = _normalize_files(files)
    user = json.dumps(
        {
            "metadata": metadata,
            "instruction": instruction,
            "files": current,
        },
        ensure_ascii=False,
    )
    raw = call_ai(system, user, temperature=0.15, language=language)
    if is_ai_unavailable(raw):
        return None
    parsed = _extract_json(raw)
    if not parsed:
        return None
    action = str(parsed.get("action") or "")
    if action not in ALLOWED_EDIT_ACTIONS:
        return None
    plan_files = _normalize_files(parsed.get("files") if isinstance(parsed.get("files"), dict) else current)
    if action != "update_website":
        return EditPlan(
            action=action,
            confidence=max(0.0, min(1.0, float(parsed.get("confidence") or 0.5))),
            files=current,
            summary=str(parsed.get("summary") or ""),
            needs_clarification=bool(parsed.get("needs_clarification")),
            clarification_question=str(parsed.get("clarification_question") or ""),
            safety_notes=[str(item) for item in parsed.get("safety_notes", []) if isinstance(item, str)],
        )
    validation = validate_website_files(plan_files)
    if not validation.valid:
        return None
    return EditPlan(
        action="update_website",
        confidence=max(0.0, min(1.0, float(parsed.get("confidence") or 0.75))),
        files=validation.files,
        summary=str(parsed.get("summary") or "Updated the website."),
        needs_clarification=False,
        clarification_question="",
        safety_notes=validation.warnings
        + [str(item) for item in parsed.get("safety_notes", []) if isinstance(item, str)],
        validation=validation,
    )


def plan_website_edit(
    *,
    current_html: str,
    current_css: str = "",
    current_js: str = "",
    metadata: dict[str, Any] | None = None,
    previous_generation_request: str = "",
    instruction: str,
    language: str = "en",
) -> EditPlan:
    files = {"index.html": current_html, "style.css": current_css, "script.js": current_js}
    if not current_html.strip():
        return EditPlan(
            action="ask_clarification",
            confidence=0.4,
            files=_normalize_files(files),
            summary="No website exists yet.",
            needs_clarification=True,
            clarification_question="Create a website first, then ask me to edit it.",
        )

    meta = dict(metadata or {})
    if previous_generation_request:
        meta["previous_generation_request"] = previous_generation_request

    ai = _ai_plan(files, meta, instruction, language)
    if ai and (ai.action != "update_website" or ai.confidence >= 0.65):
        return ai
    return _deterministic_plan(files, instruction)
