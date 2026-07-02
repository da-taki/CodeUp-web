from __future__ import annotations

import difflib
import re
from collections import Counter
from typing import Any

from codeup.services.web_learning import analyze_javascript, parse_css_rules, parse_records

RISK_LEVELS = {"low": 0, "medium": 1, "high": 2}
REVIEW_FILES = (
    ("index.html", "html_before", "html_after"),
    ("style.css", "css_before", "css_after"),
    ("script.js", "js_before", "js_after"),
)
STRUCTURE_TAGS = {"header", "nav", "main", "section", "article", "aside", "footer"}
CONTROL_TAGS = {"button", "a", "img"}
FORM_TAGS = {"form", "input", "textarea", "select"}
LAYOUT_PROPERTIES = {
    "display",
    "position",
    "grid",
    "grid-template-columns",
    "grid-template-rows",
    "flex",
    "flex-direction",
    "justify-content",
    "align-items",
    "float",
    "z-index",
}
SECRET_PATTERNS = (
    re.compile(r"\b(?:api[_-]?key|secret|token|password|private[_-]?key)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.I),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bsk-[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bghp_[0-9A-Za-z]{20,}\b"),
)


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:140]


def _risk_label(value: str) -> str:
    return value if value in RISK_LEVELS else "low"


def _max_risk(*values: str) -> str:
    return max((_risk_label(value) for value in values), key=lambda value: RISK_LEVELS[value], default="low")


def _line_stats(before: str, after: str) -> dict[str, int]:
    before_lines = (before or "").splitlines()
    after_lines = (after or "").splitlines()
    stats = {"added": 0, "removed": 0, "changed": 0}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before_lines, after_lines).get_opcodes():
        if tag == "insert":
            stats["added"] += j2 - j1
        elif tag == "delete":
            stats["removed"] += i2 - i1
        elif tag == "replace":
            stats["changed"] += max(i2 - i1, j2 - j1)
    return stats


def _stats_text(stats: dict[str, int]) -> str:
    parts = []
    if stats["added"]:
        parts.append(f"{stats['added']} added")
    if stats["removed"]:
        parts.append(f"{stats['removed']} removed")
    if stats["changed"]:
        parts.append(f"{stats['changed']} edited")
    return ", ".join(parts) if parts else "content changed"


def _changed_excerpt(before: str, after: str) -> dict[str, list[str]]:
    before_lines = (before or "").splitlines()
    after_lines = (after or "").splitlines()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before_lines, after_lines).get_opcodes():
        if tag == "equal":
            continue
        before_excerpt = [_clean_line(line) for line in before_lines[i1:i2][:4] if _clean_line(line)]
        after_excerpt = [_clean_line(line) for line in after_lines[j1:j2][:4] if _clean_line(line)]
        return {"before": before_excerpt, "after": after_excerpt}
    return {"before": [], "after": []}


def _added_secret(before: str, after: str) -> bool:
    before = before or ""
    after = after or ""
    if before == after:
        return False
    for pattern in SECRET_PATTERNS:
        after_matches = {match.group(0) for match in pattern.finditer(after)}
        before_matches = {match.group(0) for match in pattern.finditer(before)}
        if after_matches - before_matches:
            return True
    return False


def _external_refs(html: str) -> set[str]:
    refs = set()
    for match in re.finditer(r"<(?:script|link)\b[^>]*(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", html or "", re.I):
        ref = match.group(1).strip()
        if ref.startswith(("http://", "https://", "//")):
            refs.add(ref)
    return refs


def _tag_counts(html: str) -> Counter[str]:
    return Counter(record.tag for record in parse_records(html or ""))


def _tag_deltas(before: str, after: str, tags: set[str]) -> list[str]:
    before_counts = _tag_counts(before)
    after_counts = _tag_counts(after)
    details = []
    for tag in sorted(tags):
        delta = after_counts[tag] - before_counts[tag]
        if delta > 0:
            details.append(f"added {delta} <{tag}>")
        elif delta < 0:
            details.append(f"removed {-delta} <{tag}>")
    return details


def _html_file_review(before: str, after: str, stats: dict[str, int]) -> dict[str, Any]:
    details = []
    details.extend(_tag_deltas(before, after, STRUCTURE_TAGS | CONTROL_TAGS | FORM_TAGS)[:4])
    if not details and re.sub(r"<[^>]+>", " ", before or "") != re.sub(r"<[^>]+>", " ", after or ""):
        details.append("text content changed")

    risk = "low"
    reason = "HTML changed without adding behavior or risky resources."
    if _added_secret(before, after):
        risk = "high"
        reason = "Suspicious secret or token-like text was added to HTML."
    elif _external_refs(after) - _external_refs(before):
        risk = "high"
        reason = "An external script or stylesheet link was added."
    elif any(detail for detail in _tag_deltas(before, after, FORM_TAGS)):
        risk = "high"
        reason = "Form or input structure changed, which can affect submitted user data."
    elif "<body" in (before or "").lower() and "<body" not in (after or "").lower():
        risk = "high"
        reason = "The body element was removed, which can break preview/export."
    elif any(detail for detail in _tag_deltas(before, after, STRUCTURE_TAGS)):
        risk = "medium"
        reason = "Page structure changed."

    if not details:
        details.append("markup changed")
    summary = f"index.html changed ({_stats_text(stats)}): {', '.join(details[:4])}."
    return {"summary": summary, "risk": risk, "risk_reason": reason, "details": details[:4]}


def _css_properties_by_selector(css: str) -> dict[str, set[str]]:
    return {rule["selector"]: set(rule["properties"]) for rule in parse_css_rules(css or "")}


def _css_file_review(before: str, after: str, stats: dict[str, int]) -> dict[str, Any]:
    before_rules = _css_properties_by_selector(before)
    after_rules = _css_properties_by_selector(after)
    details = []
    added_selectors = sorted(set(after_rules) - set(before_rules))
    removed_selectors = sorted(set(before_rules) - set(after_rules))
    changed_properties: set[str] = set()
    if added_selectors:
        details.append(f"added selector {added_selectors[0]}")
        for selector in added_selectors:
            changed_properties.update(after_rules[selector])
    if removed_selectors:
        details.append(f"removed selector {removed_selectors[0]}")
    for selector in sorted(set(before_rules) & set(after_rules)):
        added = after_rules[selector] - before_rules[selector]
        removed = before_rules[selector] - after_rules[selector]
        if added or removed:
            changed_properties.update(added | removed)
            details.append(f"changed {selector}")
            if len(details) >= 3:
                break

    risk = "low"
    reason = "CSS changed styling without obvious layout or behavior risk."
    if _added_secret(before, after):
        risk = "high"
        reason = "Suspicious secret or token-like text was added to CSS."
    elif changed_properties & LAYOUT_PROPERTIES or "@media" in (after or "") and "@media" not in (before or ""):
        risk = "medium"
        reason = "CSS layout properties changed."

    if not details:
        details.append("style values changed")
    summary = f"style.css changed ({_stats_text(stats)}): {', '.join(details[:4])}."
    return {"summary": summary, "risk": risk, "risk_reason": reason, "details": details[:4]}


def _strip_js_comments(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js or "", flags=re.S)
    js = re.sub(r"(^|\s)//.*", "", js)
    return re.sub(r"\s+", "", js)


def _js_file_review(before: str, after: str, stats: dict[str, int]) -> dict[str, Any]:
    before_map = analyze_javascript(before or "")
    after_map = analyze_javascript(after or "")
    before_functions = {item["name"] for item in before_map["functions"]}
    after_functions = {item["name"] for item in after_map["functions"]}
    before_events = {(item["target"], item["event"]) for item in before_map["listeners"]}
    after_events = {(item["target"], item["event"]) for item in after_map["listeners"]}

    details = []
    for name in sorted(after_functions - before_functions)[:2]:
        details.append(f"added function {name}()")
    for name in sorted(before_functions - after_functions)[:2]:
        details.append(f"removed function {name}()")
    for target, event in sorted(after_events - before_events)[:2]:
        details.append(f"added {event} listener on {target}")
    for target, event in sorted(before_events - after_events)[:2]:
        details.append(f"removed {event} listener on {target}")

    before_code = _strip_js_comments(before)
    after_code = _strip_js_comments(after)
    before_lines = [line for line in (before or "").splitlines() if line.strip()]
    after_lines = [line for line in (after or "").splitlines() if line.strip()]
    form_behavior_changed = bool(
        before_code != after_code
        and re.search(r"\b(submit|preventDefault|FormData|value|input|change)\b", after or before or "")
    )
    large_rewrite = bool(
        len(before_lines) >= 8
        and (
            len(after_lines) <= max(1, len(before_lines) // 3)
            or stats["changed"] + stats["removed"] >= len(before_lines) * 0.6
        )
    )

    risk = "low"
    reason = "JavaScript comments or small non-behavioral text changed."
    if _added_secret(before, after):
        risk = "high"
        reason = "Suspicious secret or token-like text was added to JavaScript."
    elif (before or "").strip() and not (after or "").strip():
        risk = "high"
        reason = "The script was deleted."
    elif large_rewrite:
        risk = "high"
        reason = "A large script rewrite or removal was detected."
    elif form_behavior_changed:
        risk = "high"
        reason = "Form or input behavior changed."
    elif before_code != after_code:
        risk = "medium"
        reason = "JavaScript behavior changed."

    if not details:
        details.append("comments changed" if before_code == after_code else "script logic changed")
    summary = f"script.js changed ({_stats_text(stats)}): {', '.join(details[:4])}."
    return {"summary": summary, "risk": risk, "risk_reason": reason, "details": details[:4]}


def _file_review(file_name: str, before: str, after: str) -> dict[str, Any]:
    stats = _line_stats(before, after)
    if file_name == "index.html":
        review = _html_file_review(before, after, stats)
    elif file_name == "style.css":
        review = _css_file_review(before, after, stats)
    else:
        review = _js_file_review(before, after, stats)
    review.update(
        {
            "file": file_name,
            "stats": stats,
            "excerpt": _changed_excerpt(before, after),
        }
    )
    return review


def review_web_changes(
    *,
    html_before: str = "",
    html_after: str = "",
    css_before: str = "",
    css_after: str = "",
    js_before: str = "",
    js_after: str = "",
) -> dict[str, Any]:
    sources = {
        "html_before": html_before or "",
        "html_after": html_after or "",
        "css_before": css_before or "",
        "css_after": css_after or "",
        "js_before": js_before or "",
        "js_after": js_after or "",
    }
    files = []
    for file_name, before_key, after_key in REVIEW_FILES:
        before = sources[before_key]
        after = sources[after_key]
        if before == after:
            continue
        files.append(_file_review(file_name, before, after))

    if not files:
        return {
            "changed_files": [],
            "files": [],
            "risk": "low",
            "risk_reason": "No meaningful changes were detected.",
            "summary": "No meaningful changes were detected.",
        }

    risk = _max_risk(*(item["risk"] for item in files))
    risk_reason = next(item["risk_reason"] for item in files if item["risk"] == risk)
    changed_files = [item["file"] for item in files]
    summary = f"Changed {', '.join(changed_files)}. Risk: {risk}. {risk_reason}"
    return {
        "changed_files": changed_files,
        "files": files,
        "risk": risk,
        "risk_reason": risk_reason,
        "summary": summary,
    }


def _risk_line(review: dict[str, Any]) -> str:
    return f"Risk: {review.get('risk', 'low')}. {review.get('risk_reason', 'No risky change detected.')}"


def _changed_files_line(review: dict[str, Any]) -> str:
    files = review.get("changed_files") or []
    return ", ".join(files) if files else "none"


def format_web_change_review(review: dict[str, Any], mode: str = "summary") -> str:
    mode = mode if mode in {"summary", "before_after", "risk", "explain"} else "summary"
    files = review.get("files") or []
    if not files:
        return "WEB CHANGE REVIEW\n\nNo meaningful changes detected.\n" + _risk_line(review)

    if mode == "risk":
        lines = [
            "WEB CHANGE RISK",
            "",
            _risk_line(review),
            "",
            f"Changed files: {_changed_files_line(review)}",
        ]
        return "\n".join(lines)

    if mode == "explain":
        lines = [
            "WEB CHANGE EXPLANATION",
            "",
            f"Changed files: {_changed_files_line(review)}",
            "",
            "What changed:",
            *(f"- {item['summary']}" for item in files),
            "",
            "Why it matters:",
            f"- {_risk_line(review)}",
        ]
        return "\n".join(lines)

    if mode == "before_after":
        lines = [
            "WEB CHANGE REVIEW",
            "",
            f"Changed files: {_changed_files_line(review)}",
            "",
            "Before and after:",
        ]
        for item in files:
            before_excerpt = "; ".join(item["excerpt"].get("before") or ["(nothing relevant)"])
            after_excerpt = "; ".join(item["excerpt"].get("after") or ["(nothing relevant)"])
            lines.append(f"- {item['file']} before: {before_excerpt}")
            lines.append(f"- {item['file']} after: {after_excerpt}")
        lines.extend(["", _risk_line(review)])
        return "\n".join(lines)

    lines = [
        "WEB CHANGE REVIEW",
        "",
        f"Changed files: {_changed_files_line(review)}",
        "",
        "What changed:",
        *(f"- {item['summary']}" for item in files),
        "",
        _risk_line(review),
    ]
    return "\n".join(lines)


def latest_review_from_versions(versions: Any) -> dict[str, Any] | None:
    if not isinstance(versions, list) or len(versions) < 2:
        return None
    candidates = [item for item in versions if isinstance(item, dict)]
    if len(candidates) < 2:
        return None
    before = candidates[-2]
    after = candidates[-1]
    if not any(str(before.get(key) or after.get(key) or "").strip() for key in ("html", "css", "js")):
        return None
    return review_web_changes(
        html_before=str(before.get("html") or ""),
        html_after=str(after.get("html") or ""),
        css_before=str(before.get("css") or ""),
        css_after=str(after.get("css") or ""),
        js_before=str(before.get("js") or ""),
        js_after=str(after.get("js") or ""),
    )
