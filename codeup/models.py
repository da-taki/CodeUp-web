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
    issues: list[dict[str, Any]]
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


@dataclass
class ProjectVersion:
    id: str
    timestamp: str
    label: str
    source: str
    pages: dict[str, str]
    current_page: str = "home"
    summary: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectVersion:
        pages = data.get("pages", {})
        return cls(
            id=str(data.get("id") or ""),
            timestamp=str(data.get("timestamp") or ""),
            label=str(data.get("label") or "Saved version"),
            source=str(data.get("source") or "manual"),
            pages={str(key): str(value) for key, value in pages.items()} if isinstance(pages, dict) else {},
            current_page=str(data.get("current_page") or "home"),
            summary=[str(item) for item in data.get("summary", [])] if isinstance(data.get("summary"), list) else [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "label": self.label,
            "source": self.source,
            "pages": self.pages,
            "current_page": self.current_page,
            "summary": self.summary,
        }


@dataclass
class Project:
    id: str
    name: str
    created_at: str
    updated_at: str
    pages: dict[str, str] = field(default_factory=dict)
    current_page: str = "home"
    versions: list[ProjectVersion] = field(default_factory=list)
    audit_history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        pages = data.get("pages", {})
        versions = data.get("versions", [])
        audit_history = data.get("audit_history", [])
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or "Untitled Project"),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            pages={str(key): str(value) for key, value in pages.items()} if isinstance(pages, dict) else {},
            current_page=str(data.get("current_page") or "home"),
            versions=[ProjectVersion.from_dict(item) for item in versions if isinstance(item, dict)],
            audit_history=audit_history if isinstance(audit_history, list) else [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "pages": self.pages,
            "current_page": self.current_page,
            "versions": [version.to_dict() for version in self.versions],
            "audit_history": self.audit_history,
        }
