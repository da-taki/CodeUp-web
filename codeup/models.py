from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HtmlMemory:
    history: list[dict[str, Any]] = field(default_factory=list)
    last_html: str = ""
    last_url: str = ""
    last_review: str = ""
    smart_memory: list[dict[str, Any]] = field(default_factory=list)
    _hashes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HtmlMemory:
        if not isinstance(data, dict):
            return cls()
        return cls(
            history=data.get("history", []) if isinstance(data.get("history"), list) else [],
            last_html=str(data.get("last_html", "")),
            last_url=str(data.get("last_url", "")),
            last_review=str(data.get("last_review", "")),
            smart_memory=data.get("smart_memory", []) if isinstance(data.get("smart_memory"), list) else [],
            _hashes=data.get("_hashes", []) if isinstance(data.get("_hashes"), list) else [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "history": self.history,
            "last_html": self.last_html,
            "last_url": self.last_url,
            "last_review": self.last_review,
            "smart_memory": self.smart_memory,
            "_hashes": self._hashes,
        }


@dataclass
class AuditResult:
    score: int
    passed: int
    total: int
    checks: list[dict[str, Any]]
    issues: list[str]
    suggestions: list[str]
    contrast_pairs: list[dict[str, Any]]
    screen_reader_checks: list[dict[str, Any]]
    screen_reader_transcript: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "total": self.total,
            "checks": self.checks,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "contrast_pairs": self.contrast_pairs,
            "screen_reader_checks": self.screen_reader_checks,
            "screen_reader_transcript": self.screen_reader_transcript,
        }
