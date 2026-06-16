"""Session version-history reporting.

The live version stack is kept in the browser session (bounded). This module turns
a list of version records into a readable report for display and for the export ZIP.
It is read-only and never touches files.
"""

from __future__ import annotations

import re
from typing import Any

MAX_VERSIONS = 10


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_versions(versions: Any) -> list[dict[str, str]]:
    if not isinstance(versions, list):
        return []
    out: list[dict[str, str]] = []
    for item in versions:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary")
        if isinstance(summary, list):
            summary_text = "; ".join(_clean(part) for part in summary if _clean(str(part)))
        else:
            summary_text = _clean(str(summary or ""))
        out.append(
            {
                "label": _clean(item.get("label") or item.get("note") or "Saved version") or "Saved version",
                "command": _clean(item.get("command") or ""),
                "summary": summary_text,
                "timestamp": _clean(item.get("timestamp") or ""),
            }
        )
    return out[-MAX_VERSIONS:]


def build_version_history_report(versions: Any) -> str:
    normalized = normalize_versions(versions)
    lines = ["VERSION HISTORY", ""]
    if not normalized:
        lines.append("No saved versions yet. Generate or edit a website and a version will be recorded.")
        return "\n".join(lines).strip() + "\n"
    lines.append(f"You have {len(normalized)} saved version(s) in this session (most recent last):")
    for index, version in enumerate(normalized, start=1):
        detail = []
        if version["command"]:
            detail.append(f'command: "{version["command"]}"')
        if version["summary"]:
            detail.append(version["summary"])
        suffix = f" — {'; '.join(detail)}" if detail else ""
        lines.append(f"{index}. {version['label']}{suffix}")
    lines.append("")
    lines.append('Say "undo last change" to step back, or "compare versions" to hear what changed.')
    return "\n".join(lines).strip() + "\n"
