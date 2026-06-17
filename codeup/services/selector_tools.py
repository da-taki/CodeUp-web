"""Shared, deterministic helpers for matching CSS/JS selectors against HTML.

Used by the runtime teacher, the DOM/JS debugger, and the selector explainer so
all three agree on what "this selector matches that element" means. Pure
read-only analysis built on the existing ``web_learning`` parsers.
"""

from __future__ import annotations

import difflib

from codeup.services.web_learning import TagRecord, _selector_matches


def matches(selector: str, records: list[TagRecord]) -> list[TagRecord]:
    """Return the HTML records a CSS/JS selector matches (best-effort, static)."""
    return [record for record in records if _selector_matches(selector, record)]


def html_ids(records: list[TagRecord]) -> list[str]:
    return [record.attrs["id"] for record in records if record.attrs.get("id")]


def html_classes(records: list[TagRecord]) -> list[str]:
    classes: list[str] = []
    for record in records:
        classes.extend(record.attrs.get("class", "").split())
    return classes


def did_you_mean(selector: str, records: list[TagRecord]) -> str:
    """Return the closest existing id/class for a selector that matched nothing.

    Returns ``""`` when there is no close match or the selector is not a simple
    ``#id`` / ``.class`` selector.
    """
    if selector.startswith("#"):
        pool = html_ids(records)
        prefix = "#"
    elif selector.startswith("."):
        pool = html_classes(records)
        prefix = "."
    else:
        return ""
    target = selector[1:]
    if not target:
        return ""
    close = difflib.get_close_matches(target, list(dict.fromkeys(pool)), n=1, cutoff=0.6)
    return f"{prefix}{close[0]}" if close else ""
