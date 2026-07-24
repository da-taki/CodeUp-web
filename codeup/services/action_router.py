from __future__ import annotations

import json
import re
from typing import Any

from codeup.services.ai_service import call_ai, is_ai_unavailable

ALLOWED_ACTIONS = frozenset(
    {
        "append_html",
        "replace_html_element",
        "update_text",
        "add_component",
        "remove_element",
        "update_attribute",
        "add_alt_text",
        "fix_accessibility_issue",
        "generate_page",
        "edit_page",
        "preview_page",
        "explain_structure",
        "audit_accessibility",
        "sonify_structure",
        "save_snippet",
        "list_snippets",
        "load_snippet",
        "undo",
        "clear_editor",
        "unknown",
    }
)

BLOCKED_PATTERNS = re.compile(
    r"<script\b[^>]*>.*?</script>|javascript:|on\w+\s*=|eval\s*\(|document\.cookie|window\.location|fetch\s*\(|XMLHttpRequest",
    re.IGNORECASE | re.DOTALL,
)

MAX_HTML_OUTPUT = 8000
MAX_SNIPPET_NAME = 60

SYSTEM_PROMPT = """You are a structured intent mapper for CodeUp Web, a blind-first web editor.
Given a learner's voice command and the current HTML context, return ONLY valid JSON (no markdown fences, no prose).

Allowed actions: {actions}

Return exactly this JSON structure:
{{
  "action": "one of the allowed actions",
  "target": {{
    "element_type": "heading|button|image|nav|form|section|link|paragraph|null",
    "identifier": "string or null",
    "position": "end|inside_main|after_heading|before_footer|null"
  }},
  "html": "<new or replacement HTML or empty string>",
  "css": "",
  "attributes": {{}},
  "snippet_name": "name or null",
  "spoken_confirmation": "A short sentence confirming what you did.",
  "confidence": 0.0 to 1.0,
  "requires_confirmation": false
}}

Rules:
- Return JSON only. Never return markdown fences, explanations, or apologies.
- Never claim a preview succeeded or that saved snippets exist unless instructed.
- Never invent audit results.
- For generate_page or edit_page, produce complete accessible single-file HTML with embedded CSS.
- Use semantic HTML, landmarks, headings, labels, alt text, high contrast, responsive layout.
- Keep html output under {max_html} characters.
- For save_snippet/load_snippet/list_snippets, set snippet_name appropriately.
- If the intent is unclear, use action "unknown" with a helpful spoken_confirmation.
- The learner may speak English or Hinglish. Respond in the same language they used.
- For Hinglish, use natural conversational Hinglish preserving English technical terms.
"""


def _build_system(language: str) -> str:
    prompt = SYSTEM_PROMPT.format(
        actions=", ".join(sorted(ALLOWED_ACTIONS)),
        max_html=MAX_HTML_OUTPUT,
    )
    if language == "hi":
        prompt += "\nThe learner is using Hindi/Hinglish mode. Reply spoken_confirmation in natural Hinglish."
    return prompt


def _extract_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _validate(parsed: dict[str, Any]) -> dict[str, Any] | None:
    action = str(parsed.get("action", "unknown"))
    if action not in ALLOWED_ACTIONS:
        return None

    html_out = str(parsed.get("html") or "")
    if len(html_out) > MAX_HTML_OUTPUT:
        html_out = html_out[:MAX_HTML_OUTPUT]
    if BLOCKED_PATTERNS.search(html_out):
        html_out = re.sub(BLOCKED_PATTERNS, "", html_out)

    snippet_name = str(parsed.get("snippet_name") or "")
    snippet_name = re.sub(r"[^a-zA-Z0-9 _-]", "", snippet_name).strip()[:MAX_SNIPPET_NAME]

    return {
        "action": action,
        "target": parsed.get("target") or {},
        "html": html_out,
        "css": str(parsed.get("css") or ""),
        "attributes": parsed.get("attributes") if isinstance(parsed.get("attributes"), dict) else {},
        "snippet_name": snippet_name or None,
        "spoken_confirmation": str(parsed.get("spoken_confirmation") or "")[:500],
        "confidence": max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
        "requires_confirmation": bool(parsed.get("requires_confirmation")),
    }


def route_natural_command(
    transcript: str,
    current_html: str = "",
    language: str = "en",
) -> dict[str, Any] | None:
    if not transcript or not transcript.strip():
        return None

    html_context = current_html[:4000] if current_html else ""
    system = _build_system(language)
    user = f"Learner command: {transcript}\n\nCurrent HTML (truncated):\n```html\n{html_context}\n```"

    raw = call_ai(system, user, temperature=0.15, language=language)
    if is_ai_unavailable(raw):
        return None

    parsed = _extract_json(raw)
    if not parsed:
        return None

    return _validate(parsed)
