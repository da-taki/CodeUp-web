"""Selector explainer: which CSS affects an element, and which HTML a rule hits.

Answers questions like "what CSS affects the join button", "explain CSS for
hero", "which HTML uses this class", and "find unused CSS". Deterministic and
read-only; built on the existing CSS/HTML parsers so it agrees with the code map
and debugger about what matches what.
"""

from __future__ import annotations

import re
from typing import Any

from codeup.services.selector_tools import matches
from codeup.services.web_learning import (
    TagRecord,
    _selector_matches,
    _selector_should_warn_when_unmatched,
    parse_css_rules,
    parse_records,
)
from codeup.services.website_runner import clean_text

# Friendly names for common CSS properties, used in the beginner explanation.
_PROPERTY_PHRASES = {
    "background": "background",
    "background-color": "background color",
    "color": "text color",
    "padding": "inner spacing",
    "margin": "outer spacing",
    "border": "border",
    "border-radius": "rounded corners",
    "font-size": "text size",
    "font-weight": "text weight",
    "font-family": "font",
    "display": "layout mode",
    "gap": "spacing between items",
    "width": "width",
    "height": "height",
    "text-align": "text alignment",
    "box-shadow": "shadow",
    "outline": "focus outline",
}

_NOUN_TAGS = {
    "button": "button",
    "buttons": "button",
    "link": "a",
    "links": "a",
    "form": "form",
    "forms": "form",
    "nav": "nav",
    "navigation": "nav",
    "header": "header",
    "footer": "footer",
    "main": "main",
    "image": "img",
    "images": "img",
    "heading": "h1",
}

_STOP_WORDS = {
    "what",
    "which",
    "css",
    "affects",
    "affect",
    "affecting",
    "explain",
    "for",
    "the",
    "this",
    "that",
    "styles",
    "style",
    "html",
    "uses",
    "use",
    "using",
    "find",
    "show",
    "me",
    "is",
    "are",
    "on",
    "of",
    "a",
    "an",
    "to",
    "does",
}


def _clean_query(query: str) -> str:
    text = re.sub(r"[^\w\s-]", " ", (query or "").lower())
    words = [word for word in text.split() if word not in _STOP_WORDS]
    return " ".join(words).strip()


def _label(record: TagRecord) -> str:
    name = clean_text(record.name)
    bits = [record.tag]
    if record.attrs.get("id"):
        bits.append(f"#{record.attrs['id']}")
    elif record.attrs.get("class"):
        bits.append("." + record.attrs["class"].split()[0])
    label = " ".join(bits)
    return f'{label} "{name[:40]}"' if name else label


def _resolve_targets(query: str, records: list[TagRecord]) -> tuple[list[TagRecord], str]:
    """Return the HTML records the query refers to plus a human label for them."""
    cleaned = _clean_query(query)
    if not cleaned:
        return [], ""
    tokens = cleaned.split()

    # Tag nouns (button, link, form, nav, ...). Combine with any extra keyword.
    tag = next((_NOUN_TAGS[token] for token in tokens if token in _NOUN_TAGS), "")
    keywords = [token for token in tokens if token not in _NOUN_TAGS]

    def keyword_hit(record: TagRecord) -> bool:
        if not keywords:
            return True
        haystack = " ".join(
            [
                record.attrs.get("id", ""),
                record.attrs.get("class", ""),
                clean_text(record.text).lower(),
                clean_text(record.name).lower(),
            ]
        ).lower()
        return any(word in haystack for word in keywords)

    if tag:
        tags = {tag} if tag != "h1" else {f"h{level}" for level in range(1, 7)}
        found = [record for record in records if record.tag in tags and keyword_hit(record)]
        if found:
            return found, query.strip()

    # No tag noun: match id/class/text against the keywords.
    found = [record for record in records if keyword_hit(record)] if keywords else []
    # Prefer the most specific elements (ones whose id/class actually contains the keyword).
    specific = [
        record
        for record in found
        if any(word in (record.attrs.get("id", "") + " " + record.attrs.get("class", "")).lower() for word in keywords)
    ]
    return (specific or found), query.strip()


def _describe_properties(properties: list[str]) -> str:
    phrases = [_PROPERTY_PHRASES.get(prop, prop) for prop in properties if prop]
    phrases = list(dict.fromkeys(phrases))[:6]
    if not phrases:
        return "its appearance"
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"
    return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"


def _unused_css(css: str, records: list[TagRecord]) -> dict[str, Any]:
    rules = parse_css_rules(css)
    unused = [
        rule
        for rule in rules
        if _selector_should_warn_when_unmatched(rule["selector"]) and not matches(rule["selector"], records)
    ]
    lines = ["UNUSED CSS", ""]
    if not unused:
        lines.append("Every CSS rule I checked matches at least one HTML element. Nothing looks unused.")
    else:
        lines.append(f"I found {len(unused)} CSS rule(s) that do not match any HTML element:")
        lines.extend(f"- line {rule['line']}: {rule['selector']}" for rule in unused[:12])
        lines.append("")
        lines.append("Unused rules have no effect. Remove them, or fix the selector so it matches your HTML.")
    speech = (
        "I did not find any unused CSS rules."
        if not unused
        else f"I found {len(unused)} unused CSS rule{'s' if len(unused) != 1 else ''} that match nothing in your HTML."
    )
    return {
        "text": "\n".join(lines).strip() + "\n",
        "speech": speech,
        "query": "find unused CSS",
        "matched_elements": [],
        "css_selectors": [
            {"selector": rule["selector"], "line": rule["line"], "properties": rule["properties"]} for rule in unused
        ],
        "unused": True,
    }


def build_selector_explainer(html: str, css: str = "", js: str = "", query: str = "") -> dict[str, Any]:
    """Explain the CSS that affects an element (or find unused CSS).

    Returns ``text`` plus structured ``matched_elements`` and ``css_selectors``
    (each with a line number). Never mutates files.
    """
    records = parse_records(html)
    lowered = (query or "").lower()
    if "unused" in lowered:
        return _unused_css(css, records)

    targets, label = _resolve_targets(query, records)
    rules = parse_css_rules(css)

    if not targets:
        return {
            "text": (
                "SELECTOR EXPLAINER\n\n"
                f'I could not find an element matching "{clean_text(query) or "that"}". '
                'Try naming a control, for example "what CSS affects the join button" or "explain CSS for hero".\n'
            ),
            "speech": (
                f'I could not find an element matching "{clean_text(query) or "that"}". '
                "Try naming a control, like the join button."
            ),
            "query": query.strip(),
            "matched_elements": [],
            "css_selectors": [],
            "unused": False,
        }

    matched_elements = [{"element": _label(record), "tag": record.tag, "line": record.line} for record in targets[:8]]

    # Find every CSS rule that hits at least one target element.
    affecting: list[dict[str, Any]] = []
    for rule in rules:
        hit = [record for record in targets if _selector_matches(rule["selector"], record)]
        if hit:
            affecting.append(
                {
                    "selector": rule["selector"],
                    "line": rule["line"],
                    "properties": rule["properties"],
                    "declarations": rule["declarations"],
                }
            )

    first = targets[0]
    lines = [
        "SELECTOR EXPLAINER",
        "",
        f"You asked about: {clean_text(label) or first.tag}.",
        f"I found {len(targets)} matching element(s). The first is {_label(first)} on HTML line {first.line}.",
        "",
    ]
    if affecting:
        lines.append("CSS rules that affect it:")
        for rule in affecting[:8]:
            lines.append(
                f"- {rule['selector']} on CSS line {rule['line']} changes {_describe_properties(rule['properties'])}."
            )
        lines.append("")
        primary = affecting[0]
        lines.append(
            f"In plain terms: {_label(first)} is styled by {primary['selector']} (line {primary['line']}), "
            f"which sets {_describe_properties(primary['properties'])}."
        )
    else:
        lines.append("No CSS rule in style.css matches this element, so it uses the browser's default styling.")
        lines.append("You could add a rule, for example a class selector, to style it.")

    # Short spoken summary: the element and its primary rule (or that it has none).
    if affecting:
        primary = affecting[0]
        speech = (
            f"The {first.tag} is styled by {primary['selector']} on line {primary['line']}. "
            f"It changes {_describe_properties(primary['properties'])}."
        )
    else:
        speech = f"The {first.tag} has no CSS rule, so it uses the browser's default styling."

    return {
        "text": "\n".join(lines).strip() + "\n",
        "speech": speech,
        "query": query.strip(),
        "matched_elements": matched_elements,
        "css_selectors": affecting,
        "unused": False,
    }
