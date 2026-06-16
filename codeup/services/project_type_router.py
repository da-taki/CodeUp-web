from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from codeup.config import cloud_ai_enabled
from codeup.services.ai_service import call_ai, is_ai_unavailable

ALLOWED_PROJECT_TYPES = frozenset(
    {
        "portfolio",
        "school_club",
        "project_showcase",
        "event",
        "workshop",
        "small_business",
        "bakery",
        "nonprofit",
        "accessibility_project",
        "blog",
        "gallery",
        "product_page",
        "landing_page",
        "quiz_app",
        "calculator_app",
        "todo_app",
        "flashcard_app",
        "poll_page",
        "contact_form",
        "dashboard",
        "timetable",
        "habit_tracker",
        "resume",
        "generic_website",
    }
)

INTERACTIVE_PROJECT_TYPES = frozenset(
    {
        "quiz_app",
        "calculator_app",
        "todo_app",
        "flashcard_app",
        "poll_page",
        "contact_form",
        "dashboard",
        "timetable",
        "habit_tracker",
    }
)

LEGACY_KIND_BY_PROJECT_TYPE = {
    "portfolio": "portfolio",
    "resume": "portfolio",
    "school_club": "school",
    "project_showcase": "project",
    "event": "event",
    "workshop": "event",
    "small_business": "business",
    "bakery": "food",
    "nonprofit": "generic",
    "accessibility_project": "accessibility",
    "blog": "generic",
    "gallery": "portfolio",
    "product_page": "business",
    "landing_page": "business",
    "generic_website": "generic",
}

_PROJECT_TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("quiz_app", (r"\bquiz\b", r"\bquestions?\b.*\banswers?\b", r"\bmultiple choice\b")),
    ("calculator_app", (r"\bcalculator\b", r"\bcalculate\b", r"\bmath app\b", r"\bsum\b.*\bbutton\b")),
    ("todo_app", (r"\bto[- ]?do\b", r"\btodo\b", r"\btask list\b", r"\bchecklist\b")),
    ("flashcard_app", (r"\bflashcards?\b", r"\bstudy cards?\b", r"\brevision cards?\b")),
    ("poll_page", (r"\bpoll\b", r"\bvote\b", r"\bsurvey\b")),
    ("habit_tracker", (r"\bhabit\b", r"\btracker\b.*\bhabit\b", r"\bdaily streak\b")),
    ("timetable", (r"\btimetable\b", r"\bschedule\b", r"\bclass routine\b", r"\bcalendar\b")),
    ("dashboard", (r"\bdashboard\b", r"\bmetrics?\b", r"\banalytics\b", r"\bstatus board\b")),
    ("contact_form", (r"\bcontact form\b", r"\bfeedback form\b", r"\bsign[- ]?up form\b")),
    ("blog", (r"\bblog\b", r"\barticles?\b", r"\bposts?\b", r"\bjournal\b")),
    ("gallery", (r"\bgallery\b", r"\bphoto\b", r"\bimages?\b", r"\bportfolio grid\b")),
    ("product_page", (r"\bproduct\b", r"\bpricing\b", r"\bfeatures\b.*\bbuy\b", r"\bshop item\b")),
    ("landing_page", (r"\blanding page\b", r"\bcoming soon\b", r"\bwaitlist\b")),
    ("resume", (r"\bresume\b", r"\bcv\b", r"\bwork experience\b")),
    ("portfolio", (r"\bportfolio\b", r"\bpersonal site\b", r"\bmy work\b")),
    ("bakery", (r"\bbakery\b", r"\bcake\b", r"\bbread\b", r"\bcafe\b", r"\bcoffee\b")),
    ("accessibility_project", (r"\baccessibility\b", r"\ba11y\b", r"\bscreen reader\b", r"\bassistive\b")),
    ("workshop", (r"\bworkshop\b", r"\bbootcamp\b", r"\btraining\b")),
    ("event", (r"\bevent\b", r"\bconference\b", r"\bfestival\b", r"\bseminar\b")),
    ("nonprofit", (r"\bnonprofit\b", r"\bngo\b", r"\bcharity\b", r"\bfundraiser\b")),
    ("project_showcase", (r"\bproject showcase\b", r"\bscience fair\b", r"\bcapstone\b", r"\bprototype\b")),
    ("school_club", (r"\bschool club\b", r"\bclub\b", r"\bclass\b", r"\bstudent group\b")),
    ("small_business", (r"\bsmall business\b", r"\bbusiness\b", r"\bstartup\b", r"\bagency\b", r"\bstore\b")),
)


@dataclass(frozen=True)
class ProjectTypeResult:
    project_type: str
    confidence: float
    source: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_type": self.project_type,
            "confidence": self.confidence,
            "source": self.source,
            "reason": self.reason,
        }


def _extract_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.I | re.S)
    if match:
        text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def deterministic_project_type(prompt: str) -> ProjectTypeResult:
    lowered = (prompt or "").lower()
    for project_type, patterns in _PROJECT_TYPE_PATTERNS:
        if any(re.search(pattern, lowered) for pattern in patterns):
            return ProjectTypeResult(project_type, 0.9, "deterministic", f"Matched {project_type} keywords.")
    return ProjectTypeResult("generic_website", 0.55, "deterministic", "No specific project type matched.")


def _ai_project_type(prompt: str, language: str = "en") -> ProjectTypeResult | None:
    system = (
        "You classify CodeUp Web student project requests. Return strict JSON only. "
        'Schema: {"project_type":"one allowed value", "confidence":0.0, "reason":"short"}. '
        f"Allowed values: {', '.join(sorted(ALLOWED_PROJECT_TYPES))}. "
        "Do not invent new project types."
    )
    user = json.dumps({"prompt": prompt}, ensure_ascii=False)
    raw = call_ai(system, user, temperature=0.0, language=language)
    if is_ai_unavailable(raw):
        return None
    parsed = _extract_json(raw)
    if not parsed:
        return None
    project_type = str(parsed.get("project_type") or "").strip()
    if project_type not in ALLOWED_PROJECT_TYPES:
        return None
    try:
        confidence = float(parsed.get("confidence") or 0.6)
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))
    reason = str(parsed.get("reason") or "AI classification.")
    return ProjectTypeResult(project_type, confidence, "ai", reason[:160])


def classify_project_type(prompt: str, language: str = "en", use_ai: bool | None = None) -> ProjectTypeResult:
    if use_ai is None:
        use_ai = cloud_ai_enabled()
    if use_ai:
        ai_result = _ai_project_type(prompt, language)
        if ai_result and ai_result.confidence >= 0.65:
            return ai_result
    return deterministic_project_type(prompt)


def project_type_to_legacy_kind(project_type: str) -> str:
    return LEGACY_KIND_BY_PROJECT_TYPE.get(project_type, "generic")


def display_project_type(project_type: str) -> str:
    return (project_type or "generic_website").replace("_", " ").title()
