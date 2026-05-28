from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json
import os
import re
import shutil
import threading
import time
import uuid
from html import escape
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

from flask import Flask, g, jsonify, render_template, request, send_from_directory

__version__ = "1.0.0-html"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")

SESSION_COOKIE_NAME = "codeup_html_session"
SESSION_COOKIE_MAX_AGE = 3600 * 24 * 7
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = None if os.environ.get("FLASK_TESTING", "false").lower() == "true" else "Lax"

DATA_DIR = os.environ.get("DATA_DIR", ".")
MAX_REQUEST_SIZE = 1_000_000
MAX_HTML_SIZE = 100_000
MAX_MESSAGE_SIZE = 20_000
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "30"))

_ai_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="codeup-ai")
_ai_lock = threading.Lock()
_ai_active = 0
_ALLOWED_ORIGINS = {
    origin.strip().lower()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}


def safejson() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _testing_mode() -> bool:
    return os.environ.get("FLASK_TESTING", "false").lower() == "true"


def _sanitize_id(value: str | None) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]", "", value or "")[:64]
    return clean or str(uuid.uuid4())


def _env_enabled(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _flask_debug_enabled() -> bool:
    return _env_enabled("FLASK_DEBUG")


def get_session_id() -> str:
    cached = getattr(g, "session_id", None)
    if cached:
        return cached
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    session_id = _sanitize_id(cookie_value)
    g.session_id = session_id
    g.needs_session_cookie = not cookie_value or session_id != cookie_value
    return session_id


@app.after_request
def set_session_cookie(response):
    if getattr(g, "needs_session_cookie", False):
        response.set_cookie(
            SESSION_COOKIE_NAME,
            get_session_id(),
            max_age=SESSION_COOKIE_MAX_AGE,
            secure=SESSION_COOKIE_SECURE,
            httponly=SESSION_COOKIE_HTTPONLY,
            samesite=SESSION_COOKIE_SAMESITE,
        )
    return response


@app.before_request
def validate_request_size():
    if request.content_length and request.content_length > MAX_REQUEST_SIZE:
        return jsonify({"success": False, "error": "Request too large (max 1MB)"}), 413
    return None


@app.before_request
def enforce_same_origin():
    if request.method not in {"POST", "PUT", "DELETE", "PATCH"}:
        return None

    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    host = request.headers.get("Host", "").lower()

    if not origin and not referer:
        if _testing_mode():
            return None
        return jsonify({"success": False, "error": "Missing Origin/Referer header"}), 403

    if origin:
        origin_lower = origin.lower()
        origin_host = origin_lower.split("://", 1)[-1]
        if origin_host == host or origin_lower in _ALLOWED_ORIGINS:
            return None
        return jsonify({"success": False, "error": "Cross-origin request blocked"}), 403

    if referer:
        parsed = urlparse(referer)
        referer_host = parsed.netloc.lower()
        referer_origin = f"{parsed.scheme}://{parsed.netloc}".lower()
        if referer_host == host or referer_origin in _ALLOWED_ORIGINS:
            return None
        return jsonify({"success": False, "error": "Cross-origin request blocked"}), 403

    return None


def _data_path(*parts: str) -> str:
    path = os.path.join(DATA_DIR, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _html_memory_path(session_id: str | None = None) -> str:
    return _data_path("html_memory", f"{_sanitize_id(session_id or get_session_id())}.json")


def _student_site_dir(session_id: str | None = None) -> str:
    path = os.path.join(DATA_DIR, "student_sites", _sanitize_id(session_id or get_session_id()))
    os.makedirs(path, exist_ok=True)
    return path


def _safe_page_filename(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name or "page").strip("-").lower()[:48]
    if slug in {"", "home", "index"}:
        return "index.html"
    return f"{slug}.html"


def _is_safe_hosted_html_page(filename: str) -> bool:
    safe_name = os.path.basename(filename)
    return (
        safe_name == filename
        and safe_name.endswith(".html")
        and _safe_page_filename(safe_name[:-5]) == safe_name
    )


def _load_html_memory(session_id: str | None = None) -> dict[str, Any]:
    path = _html_memory_path(session_id)
    if not os.path.exists(path):
        return {"history": [], "last_html": "", "last_url": "", "last_review": ""}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return {
                "history": data.get("history", []) if isinstance(data.get("history"), list) else [],
                "last_html": str(data.get("last_html", "")),
                "last_url": str(data.get("last_url", "")),
                "last_review": str(data.get("last_review", "")),
            }
    except Exception:
        pass
    return {"history": [], "last_html": "", "last_url": "", "last_review": ""}


def _save_html_memory(data: dict[str, Any], session_id: str | None = None) -> None:
    history = data.get("history", [])
    data["history"] = history[-30:] if isinstance(history, list) else []
    path = _html_memory_path(session_id)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def _append_memory(
    prompt: str = "",
    note: str = "",
    html: str = "",
    url: str = "",
    review: str = "",
) -> dict[str, Any]:
    memory = _load_html_memory()
    if prompt or note or url:
        memory.setdefault("history", []).append(
            {"prompt": prompt, "note": note, "url": url, "timestamp": time.time()}
        )
    if html:
        memory["last_html"] = html
    if url:
        memory["last_url"] = url
    if review:
        memory["last_review"] = review
    _save_html_memory(memory)
    return memory


def _wrap_html(fragment: str) -> str:
    if "<html" in fragment.lower():
        return fragment
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>CodeUp Site</title></head>\n"
        f"<body>\n{fragment}\n</body>\n</html>"
    )


def _extract_html(text: str) -> str:
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
    return _wrap_html(candidate)


def _is_ai_unavailable(reply: str) -> bool:
    lowered = (reply or "").lower()
    return any(
        phrase in lowered
        for phrase in (
            "rate limit",
            "quota",
            "service unavailable",
            "service disabled",
            "service is busy",
            "temporarily unavailable",
            "timed out",
            "not configured",
            "api key",
            "had a problem",
        )
    )


def _fallback_chat(message: str, html: str, language: str) -> str:
    has_site = bool(html.strip())
    if language == "hi":
        if "missing" in message.lower() or "improve" in message.lower():
            return (
                "Aapki website ko aur strong banane ke liye clear heading, short sections, buttons ke labels, "
                "mobile layout, aur alt text check karein. Preview karein, phir Explain se page ka audio description sun sakte hain."
            )
        return (
            "Yeh CodeUp HTML hai. Aap bol ya type kar sakte hain: build a website for school fair, preview website, "
            "explain website, sonify website, polish HTML, pause voice, resume voice. "
            f"Abhi {'ek website editor mein hai' if has_site else 'aap nayi website bana sakte hain'}."
        )
    if "missing" in message.lower() or "improve" in message.lower():
        return (
            "Check whether the page has a clear title, useful sections, descriptive buttons, mobile spacing, "
            "image alt text, and a strong call to action. Use Preview to inspect it, then Explain for an audio description."
        )
    return (
        "This is CodeUp HTML. You can ask questions, build a website, preview it locally, hear an explanation, "
        "sonify the HTML structure, polish accessibility, and pause or resume voice commands. "
        f"{'There is already a site in the editor.' if has_site else 'Start with: Build a website for my school project.'}"
    )


def _title_from_prompt(prompt: str) -> str:
    cleaned = re.sub(r"(?i)\b(build|make|create|generate)\b", "", prompt)
    cleaned = re.sub(r"(?i)\b(a|an|the)?\s*(website|site|webpage|page)\s*(for|about)?\b", "", cleaned)
    words = [word.strip(" ,.-_") for word in cleaned.split() if word.strip(" ,.-_")]
    title = " ".join(words[:8]).strip() or "My CodeUp Website"
    return title.title()


def _fallback_site(prompt: str) -> str:
    title = _title_from_prompt(prompt)
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


def _fallback_explanation(html: str, language: str) -> str:
    headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, flags=re.IGNORECASE | re.DOTALL)
    clean_headings = [re.sub(r"<[^>]+>", "", heading).strip() for heading in headings if heading.strip()]
    summary = ", ".join(clean_headings[:5]) or "the current page sections"
    if language == "hi":
        return (
            f"Yeh website {summary} par based hai. Page mein structured headings, content sections, aur local preview hai. "
            "Demo ke liye contrast, mobile spacing, button labels, aur image alt text zaroor check karein."
        )
    return (
        f"This website is organized around {summary}. It has a structured page, readable sections, and a local preview. "
        "Before demoing, check contrast, mobile spacing, button labels, and image alt text."
    )


def _fallback_review(html: str, language: str) -> str:
    audit = _audit_html(html)
    headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, flags=re.IGNORECASE | re.DOTALL)
    clean_headings = [re.sub(r"<[^>]+>", "", heading).strip() for heading in headings if heading.strip()]
    sections = ", ".join(clean_headings[:5]) or "the current page"
    missing = []
    lowered = html.lower()
    if "contact" not in lowered:
        missing.append("a contact or next-step section")
    if not re.search(r"<a\b[^>]*>|<button\b", html, re.IGNORECASE):
        missing.append("a clear call-to-action button or link")
    if "schedule" not in lowered and "event" in lowered:
        missing.append("event timing or schedule details")
    if audit["score"] < 100:
        missing.extend(audit["suggestions"][:2])
    if not missing:
        missing.append("real photos with alt text or more specific student details")

    if language == "hi":
        return (
            f"Visual review: website {sections} ke around organized hai. Layout clear hai, sections readable hain, "
            f"aur accessibility score {audit['score']}/100 hai. Missing: {', '.join(missing[:3])}. "
            "Aap bol sakte hain: add that, fix missing things, ya make it more polished."
        )
    return (
        f"Visual review: the website is organized around {sections}. It has a clear layout, readable sections, "
        f"and an accessibility score of {audit['score']}/100. What is missing: {', '.join(missing[:3])}. "
        "Say or type: add that, fix missing things, or make it more polished."
    )


def _fallback_apply_review(html: str, instruction: str, review: str) -> str:
    wrapped = _wrap_html(html)
    block = """
    <section aria-labelledby="next-steps-heading">
      <h2 id="next-steps-heading">Next Steps</h2>
      <p>This section was added from the review loop. It gives visitors a clear action after reading the page.</p>
      <ul>
        <li>Add real dates, timings, or contact details for the student project.</li>
        <li>Use descriptive button text so screen reader users understand the action.</li>
        <li>Add images only with useful alt text.</li>
      </ul>
      <a class="button" href="mailto:hello@example.com">Contact the team</a>
    </section>
"""
    if "Next Steps" in wrapped:
        return wrapped
    if re.search(r"</main\s*>", wrapped, flags=re.IGNORECASE):
        return re.sub(r"</main\s*>", block + "\n  </main>", wrapped, count=1, flags=re.IGNORECASE)
    return re.sub(r"</body\s*>", block + "\n</body>", wrapped, count=1, flags=re.IGNORECASE)


def _html_text(html: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(hex_color: str) -> float:
        value = hex_color.strip().lstrip("#")
        if len(value) == 3:
            value = "".join(char * 2 for char in value)
        if len(value) != 6:
            return 0.0
        channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light = max(luminance(foreground), luminance(background))
    dark = min(luminance(foreground), luminance(background))
    return round((light + 0.05) / (dark + 0.05), 2)


def _contrast_pairs(html: str) -> list[dict[str, Any]]:
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
            ratio = _contrast_ratio(color, background)
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
                "ratio": _contrast_ratio("#17202a", "#ffffff"),
                "passes_aa": True,
            }
        )
    return pairs[:12]


def _screen_reader_checks(html: str) -> list[dict[str, Any]]:
    lowered = html.lower()
    headings = [int(level) for level in re.findall(r"<h([1-6])\b", html, flags=re.IGNORECASE)]
    skipped_heading = any(next_level - level > 1 for level, next_level in zip(headings, headings[1:]))
    controls = re.findall(r"<(button|a|input|textarea|select)\b([^>]*)>(.*?)</\1>|<(input)\b([^>]*)>", html, flags=re.IGNORECASE | re.DOTALL)
    unnamed = 0
    for match in controls:
        attrs = (match[1] or "") + " " + (match[4] or "")
        text = _html_text(match[2] or "")
        if not text and not re.search(r"\b(aria-label|title|placeholder|alt)\s*=", attrs, re.IGNORECASE):
            unnamed += 1
    return [
        {"pattern": "NVDA heading navigation", "passed": bool(headings) and not skipped_heading, "note": "Headings exist and do not skip levels." if bool(headings) and not skipped_heading else "Add ordered headings so students can skim by heading."},
        {"pattern": "JAWS landmark navigation", "passed": any(tag in lowered for tag in ("<main", "<nav", "<header", "<footer")), "note": "Semantic landmarks are present."},
        {"pattern": "VoiceOver control names", "passed": unnamed == 0, "note": "Interactive controls expose names." if unnamed == 0 else f"{unnamed} controls may be announced without a useful name."},
    ]


def _screen_reader_transcript(html: str) -> list[dict[str, str]]:
    body = re.search(r"<body\b[^>]*>(.*?)</body>", html, flags=re.IGNORECASE | re.DOTALL)
    source = body.group(1) if body else html
    token_pattern = re.compile(r"<(header|nav|main|footer|section|article|form|h[1-6]|a|button|img|input|textarea|select)\b([^>]*)>", flags=re.IGNORECASE)
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
    for match in token_pattern.finditer(source):
        tag = match.group(1).lower()
        attrs = match.group(2) or ""
        inner = ""
        if tag not in {"img", "input"}:
            close = re.search(rf"</{tag}>", source[match.end() :], flags=re.IGNORECASE)
            if close:
                inner = source[match.end() : match.end() + close.start()]
        text = (
            re.search(r"\baria-label\s*=\s*['\"]([^'\"]+)", attrs, re.IGNORECASE)
            or re.search(r"\balt\s*=\s*['\"]([^'\"]*)", attrs, re.IGNORECASE)
            or re.search(r"\bplaceholder\s*=\s*['\"]([^'\"]+)", attrs, re.IGNORECASE)
            or re.search(r"\btitle\s*=\s*['\"]([^'\"]+)", attrs, re.IGNORECASE)
        )
        name = text.group(1).strip() if text else _html_text(inner)
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
        transcript.append({"tag": "document", "role": "document", "name": "", "announcement": "document, no readable body content"})
    return transcript


def _audit_html(html: str) -> dict[str, Any]:
    lowered = html.lower()
    images = re.findall(r"<img\b[^>]*>", html, flags=re.IGNORECASE)
    links = re.findall(r"<a\b[^>]*>(.*?)</a>", html, flags=re.IGNORECASE | re.DOTALL)
    buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", html, flags=re.IGNORECASE | re.DOTALL)
    headings = re.findall(r"<h([1-6])\b[^>]*>(.*?)</h\1>", html, flags=re.IGNORECASE | re.DOTALL)
    checks = [
        ("Document starts with doctype", lowered.lstrip().startswith("<!doctype html")),
        ("Page has a language attribute", bool(re.search(r"<html\b[^>]*\blang=", html, re.IGNORECASE))),
        ("Page has a title", bool(re.search(r"<title>\s*[^<]+", html, re.IGNORECASE))),
        ("Page has a viewport meta tag", "name=\"viewport\"" in lowered or "name='viewport'" in lowered),
        ("Page has an h1 heading", bool(re.search(r"<h1\b", html, re.IGNORECASE))),
        ("Images have alt text", all(re.search(r"\balt\s*=\s*['\"][^'\"]+['\"]", image, re.IGNORECASE) for image in images)),
        ("Buttons have readable labels", all(_html_text(button) for button in buttons)),
        ("Links have readable labels", all(_html_text(link) for link in links)),
        ("Uses semantic sections", any(tag in lowered for tag in ("<main", "<section", "<article", "<header", "<footer"))),
    ]
    passed = sum(1 for _, ok in checks if ok)
    issues = [label for label, ok in checks if not ok]
    suggestions = []
    if not headings:
        suggestions.append("Add headings so screen reader users can skim the page.")
    if images and "Images have alt text" in issues:
        suggestions.append("Add meaningful alt text to every image.")
    if "Uses semantic sections" in issues:
        suggestions.append("Use main, section, header, and footer landmarks.")
    if not suggestions:
        suggestions.append("Preview the page on mobile and ask a student to describe what they hear.")
    contrast_pairs = _contrast_pairs(html)
    screen_reader_checks = _screen_reader_checks(html)
    screen_reader_transcript = _screen_reader_transcript(html)
    if any(not pair["passes_aa"] for pair in contrast_pairs):
        suggestions.append("Increase text/background contrast until each normal text pair is at least 4.5:1.")
    if any(not check["passed"] for check in screen_reader_checks):
        suggestions.append("Run the page by headings, landmarks, and control names to match common screen reader navigation patterns.")
    return {
        "score": round((passed / len(checks)) * 100),
        "passed": passed,
        "total": len(checks),
        "checks": [{"label": label, "passed": ok} for label, ok in checks],
        "issues": issues,
        "suggestions": suggestions,
        "contrast_pairs": contrast_pairs,
        "screen_reader_checks": screen_reader_checks,
        "screen_reader_transcript": screen_reader_transcript,
    }


def _call_ollama(system_prompt: str, user_prompt: str, temperature: float) -> str | None:
    if os.environ.get("OLLAMA_ENABLED", "0") != "1":
        return None
    try:
        import requests

        response = requests.post(
            f"{os.environ.get('OLLAMA_URL', 'http://localhost:11434').rstrip('/')}/api/chat",
            json={
                "model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"temperature": temperature, "num_predict": 4096},
                "stream": False,
            },
            timeout=AI_TIMEOUT,
        )
        response.raise_for_status()
        content = (response.json().get("message") or {}).get("content", "").strip()
        return content or None
    except Exception:
        return None


def call_ai(system_prompt: str, user_prompt: str, temperature: float = 0.25, language: str = "en") -> str:
    if os.environ.get("GEMINI_ENABLED", "1") != "1":
        local = _call_ollama(system_prompt, user_prompt, temperature)
        return local or "AI service disabled"

    xai_key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    if not xai_key and not groq_key:
        local = _call_ollama(system_prompt, user_prompt, temperature)
        return local or "AI service not configured. Please set XAI_API_KEY, GROK_API_KEY, or GROQ_API_KEY."

    prompt = system_prompt
    if language == "hi":
        prompt = f"Reply in natural Hindi or Hinglish for a blind student. {system_prompt}"

    def run_call() -> str:
        global _ai_active
        with _ai_lock:
            _ai_active += 1
        try:
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_prompt},
            ]
            if xai_key:
                import requests

                response = requests.post(
                    os.environ.get("XAI_API_URL", "https://api.x.ai/v1/chat/completions"),
                    headers={"Authorization": f"Bearer {xai_key}", "Content-Type": "application/json"},
                    json={
                        "model": os.environ.get("XAI_MODEL", os.environ.get("GROK_MODEL", "grok-3-mini")),
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": 4096,
                    },
                    timeout=AI_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()

            from groq import Groq

            response = Groq(api_key=groq_key).chat.completions.create(
                model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=messages,
                temperature=temperature,
                max_tokens=4096,
            )
            return response.choices[0].message.content.strip()
        finally:
            with _ai_lock:
                _ai_active -= 1

    with _ai_lock:
        if _ai_active >= 3:
            local = _call_ollama(system_prompt, user_prompt, temperature)
            return local or "AI service is busy. Please try again in a moment."

    future = _ai_executor.submit(run_call)
    try:
        return future.result(timeout=AI_TIMEOUT + 1)
    except Exception as exc:
        local = _call_ollama(system_prompt, user_prompt, temperature)
        return local or f"AI service had a problem: {str(exc)[:120]}"


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/ide")
def ide():
    return render_template("index.html")


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok", "version": __version__})


@app.route("/api-config", methods=["POST"])
def api_config():
    body = safejson()
    key = str(body.get("apiKey") or body.get("xaiKey") or "").strip()
    if key:
        os.environ["XAI_API_KEY"] = key
    return jsonify({"success": True, "provider": "xAI/Grok" if key else "environment"})


@app.route("/publish-site", methods=["POST"])
def publish_site():
    body = safejson()
    html = str(body.get("html") or "")
    raw_pages = body.get("pages")
    pages: dict[str, str] = {}
    if isinstance(raw_pages, dict):
        for name, page_html in raw_pages.items():
            page_name = str(name or "page").strip() or "page"
            page_value = str(page_html or "")
            if not page_value.strip():
                continue
            pages[page_name] = page_value
    if not pages and html.strip():
        pages["home"] = html
    total_size = sum(len(page_html) for page_html in pages.values())
    if total_size > MAX_HTML_SIZE * 5:
        return jsonify({"success": False, "error": f"Website too large (max {MAX_HTML_SIZE * 5} bytes)"}), 413
    if not pages:
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400

    session_id = get_session_id()
    site_dir = _student_site_dir(session_id)
    page_urls = {}
    last_html = ""
    for name, page_html in pages.items():
        if len(page_html) > MAX_HTML_SIZE:
            return jsonify({"success": False, "error": f"Page {name} too large (max {MAX_HTML_SIZE} bytes)"}), 413
        wrapped = _wrap_html(page_html)
        filename = _safe_page_filename(name)
        with open(os.path.join(site_dir, filename), "w", encoding="utf-8") as handle:
            handle.write(wrapped)
        page_urls[name] = f"/student-site/{session_id}/{'' if filename == 'index.html' else filename}"
        if filename == "index.html" or not last_html:
            last_html = wrapped

    url = f"/student-site/{session_id}/"
    _append_memory(note=f"Published website preview with {len(pages)} page(s)", html=last_html, url=url)
    return jsonify({"success": True, "url": url, "pages": page_urls})


@app.route("/student-site/<session_id>/")
def student_site(session_id: str):
    return send_from_directory(_student_site_dir(_sanitize_id(session_id)), "index.html")


@app.route("/student-site/<session_id>/<path:filename>")
def student_site_page(session_id: str, filename: str):
    if not _is_safe_hosted_html_page(filename):
        return jsonify({"success": False, "error": "Page not found"}), 404
    return send_from_directory(_student_site_dir(_sanitize_id(session_id)), filename)


@app.route("/html-memory", methods=["GET", "POST"])
def html_memory():
    if request.method == "GET":
        return jsonify({"success": True, "memory": _load_html_memory()})

    body = safejson()
    html = str(body.get("html") or "")
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    memory = _append_memory(
        prompt=str(body.get("prompt") or "").strip(),
        note=str(body.get("note") or "").strip(),
        html=html,
        url=str(body.get("url") or "").strip(),
    )
    return jsonify({"success": True, "memory": memory})


@app.route("/reset-session", methods=["POST"])
def reset_session():
    session_id = get_session_id()
    for path in (_html_memory_path(session_id),):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    site_dir = _student_site_dir(session_id)
    try:
        if os.path.isdir(site_dir):
            shutil.rmtree(site_dir)
    except OSError:
        pass
    return jsonify({"success": True, "memory": _load_html_memory(session_id)})


@app.route("/html-audit", methods=["POST"])
def html_audit():
    html = str(safejson().get("html") or "")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    audit = _audit_html(html)
    _append_memory(note=f"Accessibility audit score {audit['score']}", html=html)
    return jsonify({"success": True, "audit": audit})


@app.route("/review-site", methods=["POST"])
def review_site():
    body = safejson()
    html = str(body.get("html") or body.get("code") or "")
    language = str(body.get("language") or "en")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413

    audit = _audit_html(html)
    system = (
        "You are the sighted reviewer inside CodeUp HTML for blind and visually impaired students. "
        "Describe the current website visually, then say what is missing, then suggest exactly what to add next. "
        "Keep it conversational, concrete, and short enough to be spoken aloud. Do not return code."
    )
    user = (
        f"Accessibility audit score: {audit['score']}/100\n"
        f"Audit suggestions: {', '.join(audit['suggestions'])}\n\n"
        f"Current HTML:\n```html\n{html[:MAX_HTML_SIZE]}\n```"
    )
    review = call_ai(system, user, temperature=0.25, language=language)
    if _is_ai_unavailable(review):
        review = _fallback_review(html, language)
    memory = _append_memory(note=f"Review loop score {audit['score']}", html=html, review=review)
    return jsonify({"success": True, "review": review, "audit": audit, "memory": memory})


@app.route("/apply-review", methods=["POST"])
def apply_review():
    body = safejson()
    html = str(body.get("html") or body.get("code") or "")
    instruction = str(body.get("instruction") or "Apply the latest review suggestions").strip()
    review = str(body.get("review") or "")
    language = str(body.get("language") or "en")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty", "code": ""}), 400
    if len(html) > MAX_HTML_SIZE or len(instruction) > MAX_MESSAGE_SIZE or len(review) > MAX_MESSAGE_SIZE:
        return jsonify({"success": False, "error": "Request too large", "code": ""}), 413

    memory = _load_html_memory()
    latest_review = review or memory.get("last_review", "")
    system = (
        "You are CodeUp HTML's review-loop editor. Return one complete accessible single-file HTML document. "
        "Apply the student's instruction using the latest visual review. Keep the page semantic, responsive, "
        "high contrast, and understandable for screen reader users. Do not return markdown fences or prose."
    )
    user = (
        f"Student instruction:\n{instruction}\n\n"
        f"Latest review:\n{latest_review or 'No review yet. Add useful next steps and accessibility improvements.'}\n\n"
        f"Current HTML:\n```html\n{html[:MAX_HTML_SIZE]}\n```"
    )
    raw = call_ai(system, user, temperature=0.25, language=language)
    fixed = _fallback_apply_review(html, instruction, latest_review) if _is_ai_unavailable(raw) else _extract_html(raw)
    memory = _append_memory(prompt=instruction, note="Applied review suggestions", html=fixed)
    return jsonify({"success": True, "code": fixed, "language": "html", "memory": memory})


@app.route("/html-chat", methods=["POST"])
def html_chat():
    body = safejson()
    message = str(body.get("message") or "").strip()
    html = str(body.get("html") or "")
    language = str(body.get("language") or "en")

    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty"}), 400
    if len(message) > MAX_MESSAGE_SIZE:
        return jsonify({"success": False, "error": f"Message too large (max {MAX_MESSAGE_SIZE} bytes)"}), 413
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413

    memory = _load_html_memory()
    current_html = html or memory.get("last_html", "")
    recent = "\n".join(
        f"- {item.get('prompt') or item.get('note')}"
        for item in memory.get("history", [])[-8:]
        if isinstance(item, dict)
    )
    system = (
        "You are CodeUp HTML, a conversational website-building guide for blind and visually impaired students. "
        "Explain what students can do, describe the current page, suggest improvements, and keep responses short enough for speech. "
        "Do not return code from chat; for building, tell the student to say or type 'Build a website for ...'."
    )
    user = (
        f"Student message:\n{message}\n\n"
        f"Current local URL:\n{memory.get('last_url') or 'No preview yet.'}\n\n"
        f"Recent memory:\n{recent or 'No previous actions.'}\n\n"
        f"Current HTML:\n```html\n{current_html[:MAX_HTML_SIZE]}\n```"
    )
    reply = call_ai(system, user, temperature=0.25, language=language)
    if _is_ai_unavailable(reply):
        reply = _fallback_chat(message, current_html, language)
    updated = _append_memory(prompt=message, note="chat", html=html)
    return jsonify({"success": True, "reply": reply, "memory": updated})


@app.route("/generate-code", methods=["POST"])
def generate_code():
    body = safejson()
    prompt = str(body.get("prompt") or body.get("task") or "").strip()
    current_html = str(body.get("code") or body.get("html") or body.get("current_html") or "")
    language = str(body.get("language") or "en")

    if not prompt:
        return jsonify({"success": False, "error": "Prompt cannot be empty", "code": ""}), 400
    if len(prompt) > MAX_MESSAGE_SIZE or len(current_html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": "Request too large", "code": ""}), 413

    memory = _load_html_memory()
    system = (
        "You are CodeUp HTML's website generator for blind school students. "
        "Return one complete accessible single-file HTML document with embedded CSS and small JavaScript only when useful. "
        "Use semantic landmarks, headings, labels, readable contrast, responsive layout, and clear visible content. "
        "Do not return markdown fences or explanations."
    )
    user = (
        f"Build request:\n{prompt}\n\n"
        f"Existing HTML, if this is an edit:\n```html\n{(current_html or memory.get('last_html', ''))[:MAX_HTML_SIZE]}\n```"
    )
    raw = call_ai(system, user, temperature=0.35, language=language)
    html = _fallback_site(prompt) if _is_ai_unavailable(raw) else _extract_html(raw)
    _append_memory(prompt=prompt, note="Generated website", html=html)
    return jsonify({"success": True, "code": html, "language": "html"})


@app.route("/analyze", methods=["POST"])
def analyze():
    body = safejson()
    html = str(body.get("code") or body.get("html") or "")
    language = str(body.get("language") or "en")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    system = (
        "Explain this HTML website to a blind beginner. Describe what it looks like, its sections, "
        "how a visitor would move through it, and one or two accessibility improvements."
    )
    explanation = call_ai(system, f"```html\n{html[:MAX_HTML_SIZE]}\n```", temperature=0.2, language=language)
    if _is_ai_unavailable(explanation):
        explanation = _fallback_explanation(html, language)
    _append_memory(note="Explained website", html=html)
    return jsonify({"success": True, "analysis": explanation, "explanation": explanation})


@app.route("/fix", methods=["POST"])
def fix():
    body = safejson()
    html = str(body.get("code") or body.get("html") or "")
    language = str(body.get("language") or "en")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty", "code": ""}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)", "code": ""}), 413
    system = (
        "You are an expert accessibility-focused HTML/CSS/JavaScript reviewer. "
        "Return a complete improved single-file HTML document. Fix accessibility, layout, responsiveness, and clarity. "
        "Do not return markdown fences or prose."
    )
    raw = call_ai(system, f"```html\n{html[:MAX_HTML_SIZE]}\n```", temperature=0.2, language=language)
    fixed = _wrap_html(html) if _is_ai_unavailable(raw) else _extract_html(raw)
    _append_memory(note="Polished HTML", html=fixed)
    return jsonify({"success": True, "code": fixed, "language": "html"})


@app.route("/voice-command", methods=["POST"])
def voice_command():
    text = str(safejson().get("text") or "").strip()
    lower = text.lower()
    if not text:
        return jsonify({"success": True, "action": "unknown", "message": "No command heard"})
    if "wake word" in lower:
        action = "set_wake_word"
    elif "next heading" in lower or "previous heading" in lower or "next section" in lower or "previous section" in lower or re.search(r"read paragraph\s+\d+", lower):
        action = "navigate_page"
    elif "high contrast" in lower:
        action = "edit_css"
    elif "contrast" in lower:
        action = "announce_contrast"
    elif "what is a div" in lower or "aria-label" in lower or "what does" in lower:
        action = "explain_concept"
    elif "go back" in lower or lower.startswith("undo"):
        action = "undo_version"
    elif "what changed" in lower or "compare versions" in lower or "review changes" in lower:
        action = "review_changes"
    elif "multi page" in lower or "multiple page" in lower:
        action = "create_multipage_site"
    elif "go to page" in lower or "switch to page" in lower:
        action = "switch_page"
    elif "template" in lower:
        action = "use_template"
    elif (
        "make the heading" in lower
        or "make heading" in lower
        or "change the background" in lower
        or "background" in lower
        or "font" in lower
        or "text color" in lower
        or "more spacing" in lower
        or "less spacing" in lower
        or "rounded" in lower
        or "center" in lower
    ):
        action = "edit_css"
    elif "pause voice" in lower:
        action = "pause_voice"
    elif "resume voice" in lower or "voice on" in lower:
        action = "resume_voice"
    elif "stop speaking" in lower or "quiet" in lower:
        action = "stop_speaking"
    elif "preview" in lower or "show website" in lower:
        action = "preview_site"
    elif "audit" in lower or "accessibility" in lower:
        action = "audit_site"
    elif "outline" in lower or "page structure" in lower:
        action = "outline_site"
    elif "export" in lower or "download" in lower:
        action = "export_site"
    elif "reset session" in lower or lower == "reset":
        action = "reset_session"
    elif "add that" in lower or "apply that" in lower or "fix missing" in lower:
        action = "apply_review"
    elif "missing" in lower or "review" in lower or "what do you think" in lower:
        action = "review_site"
    elif "explain" in lower or "describe" in lower:
        action = "explain_site"
    elif "sonify" in lower or "sound" in lower:
        action = "sonify_site"
    elif re.search(r"\b(build|make|create|generate)\b.*\b(website|site|page)\b", lower):
        action = "build_site"
    else:
        action = "chat"
    return jsonify({"success": True, "action": action, "text": text})


if __name__ == "__main__":
    app.run(debug=_flask_debug_enabled())
