from __future__ import annotations

import difflib

from codeup.services.web_learning import TagRecord, _selector_matches


def matches(selector: str, records: list[TagRecord]) -> list[TagRecord]:
    return [record for record in records if _selector_matches(selector, record)]


def html_ids(records: list[TagRecord]) -> list[str]:
    return [record.attrs["id"] for record in records if record.attrs.get("id")]


def html_classes(records: list[TagRecord]) -> list[str]:
    classes: list[str] = []
    for record in records:
        classes.extend(record.attrs.get("class", "").split())
    return classes


def did_you_mean(selector: str, records: list[TagRecord]) -> str:
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
