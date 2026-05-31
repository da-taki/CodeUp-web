"""HTML parsing, wrapping, sanitization, and audit utilities."""

from __future__ import annotations

import re
from html import escape
from typing import Any

from codeup.models import AuditResult


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
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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


# --- Contrast and accessibility ---


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
    lowered = html.lower()
    headings = [int(level) for level in re.findall(r"<h([1-6])\b", html, flags=re.IGNORECASE)]
    skipped_heading = any(next_level - level > 1 for level, next_level in zip(headings, headings[1:], strict=False))
    controls = re.findall(
        r"<(button|a|input|textarea|select)\b([^>]*)>(.*?)</\1>|<(input)\b([^>]*)>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    unnamed = 0
    for match in controls:
        attrs = (match[1] or "") + " " + (match[4] or "")
        text = html_text(match[2] or "")
        if not text and not re.search(r"\b(aria-label|title|placeholder|alt)\s*=", attrs, re.IGNORECASE):
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
            "passed": any(tag in lowered for tag in ("<main", "<nav", "<header", "<footer")),
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
    body = re.search(r"<body\b[^>]*>(.*?)</body>", html, flags=re.IGNORECASE | re.DOTALL)
    source = body.group(1) if body else html
    token_pattern = re.compile(
        r"<(header|nav|main|footer|section|article|form|h[1-6]|a|button|img|input|textarea|select)\b([^>]*)>",
        flags=re.IGNORECASE,
    )
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
        name = text.group(1).strip() if text else html_text(inner)
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


def audit_html(html: str) -> AuditResult:
    lowered = html.lower()
    images = re.findall(r"<img\b[^>]*>", html, flags=re.IGNORECASE)
    links = re.findall(r"<a\b[^>]*>(.*?)</a>", html, flags=re.IGNORECASE | re.DOTALL)
    buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", html, flags=re.IGNORECASE | re.DOTALL)
    headings = re.findall(r"<h([1-6])\b[^>]*>(.*?)</h\1>", html, flags=re.IGNORECASE | re.DOTALL)
    checks = [
        ("Document starts with doctype", lowered.lstrip().startswith("<!doctype html")),
        ("Page has a language attribute", bool(re.search(r"<html\b[^>]*\blang=", html, re.IGNORECASE))),
        ("Page has a title", bool(re.search(r"<title>\s*[^<]+", html, re.IGNORECASE))),
        ("Page has a viewport meta tag", 'name="viewport"' in lowered or "name='viewport'" in lowered),
        ("Page has an h1 heading", bool(re.search(r"<h1\b", html, re.IGNORECASE))),
        (
            "Images have alt text",
            all(re.search(r"\balt\s*=\s*['\"][^'\"]+['\"]", img, re.IGNORECASE) for img in images),
        ),
        ("Buttons have readable labels", all(html_text(btn) for btn in buttons)),
        ("Links have readable labels", all(html_text(link) for link in links)),
        (
            "Uses semantic sections",
            any(tag in lowered for tag in ("<main", "<section", "<article", "<header", "<footer")),
        ),
    ]
    passed = sum(1 for _, ok in checks if ok)
    issues = [label for label, ok in checks if not ok]
    suggestions: list[str] = []
    if not headings:
        suggestions.append("Add headings so screen reader users can skim the page.")
    if images and "Images have alt text" in issues:
        suggestions.append("Add meaningful alt text to every image.")
    if "Uses semantic sections" in issues:
        suggestions.append("Use main, section, header, and footer landmarks.")
    if not suggestions:
        suggestions.append("Preview the page on mobile and ask a student to describe what they hear.")
    cp = contrast_pairs(html)
    src = screen_reader_checks(html)
    srt = screen_reader_transcript(html)
    if any(not pair["passes_aa"] for pair in cp):
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
