from __future__ import annotations

from typing import Any

TUTORIAL_TRACKS: dict[str, dict[str, Any]] = {
    "html": {
        "title": "HTML tutorial",
        "steps": [
            {
                "title": "Create a simple page",
                "say": "Start with a real page so we have something to read.",
                "command": "make a website for my school robotics club",
            },
            {
                "title": "Understand headings",
                "say": "Headings give the page an outline screen readers can jump through.",
                "command": "code map",
            },
            {
                "title": "Add a section",
                "say": "More sections mean more meaning for the reader.",
                "command": "add a section about competitions",
            },
            {
                "title": "Map the code",
                "say": "See the landmarks, headings, and controls you created.",
                "command": "code map",
            },
        ],
    },
    "css": {
        "title": "CSS tutorial",
        "steps": [
            {
                "title": "Create a styled page",
                "say": "Generate a site so there is CSS to explore.",
                "command": "make a portfolio website",
            },
            {
                "title": "Explain the CSS",
                "say": "Learn how selectors connect style to your HTML.",
                "command": "explain CSS",
            },
            {
                "title": "Change the design",
                "say": "Try a visual change and notice the difference.",
                "command": "make it more professional",
            },
            {
                "title": "Describe the design",
                "say": "Hear a non-visual description of how it looks.",
                "command": "describe the design",
            },
        ],
    },
    "javascript": {
        "title": "JavaScript tutorial",
        "steps": [
            {
                "title": "Create an interactive app",
                "say": "A quiz app gives us real JavaScript to study.",
                "command": "make a quiz app about Python basics",
            },
            {
                "title": "Explain the JavaScript",
                "say": "Learn how an event listener reacts to a click.",
                "command": "explain JavaScript",
            },
            {
                "title": "Run the website",
                "say": "Get a summary of what happens when it runs.",
                "command": "run website",
            },
            {
                "title": "Debug the website",
                "say": "Check for errors like a teacher would.",
                "command": "debug this website",
            },
        ],
    },
    "accessibility": {
        "title": "Accessibility tutorial",
        "steps": [
            {
                "title": "Create a simple site",
                "say": "We need a page to test for accessibility.",
                "command": "make a website for my school robotics club",
            },
            {
                "title": "Check accessibility",
                "say": "Run the audit and read the issues.",
                "command": "check accessibility",
            },
            {"title": "Screen reader tour", "say": "Hear the likely reading order.", "command": "screen reader tour"},
            {
                "title": "Keyboard test",
                "say": "Check that everything is reachable by keyboard.",
                "command": "test keyboard navigation",
            },
            {
                "title": "Fix accessibility issues",
                "say": "Apply the safe fixes and compare.",
                "command": "fix accessibility issues",
            },
        ],
    },
    "forms": {
        "title": "Forms tutorial",
        "steps": [
            {"title": "Add a contact form", "say": "Forms let visitors reach you.", "command": "add a contact form"},
            {
                "title": "Explain labels",
                "say": "Labels tell screen readers what each field is for.",
                "command": "explain CSS",
            },
            {
                "title": "Keyboard test",
                "say": "Make sure the form is usable without a mouse.",
                "command": "test keyboard navigation",
            },
            {
                "title": "Check accessibility",
                "say": "Confirm the form passes the audit.",
                "command": "check accessibility",
            },
        ],
    },
    "export": {
        "title": "Export tutorial",
        "steps": [
            {"title": "Create a site", "say": "Make something worth exporting.", "command": "make a bakery website"},
            {"title": "Learning notes", "say": "Capture what the project teaches.", "command": "learning notes"},
            {
                "title": "Export the website",
                "say": "Download the ZIP with code and notes.",
                "command": "export website",
            },
            {
                "title": "Explain the ZIP",
                "say": "Learn what each exported file is for.",
                "command": "explain the ZIP contents",
            },
        ],
    },
}

_TRACK_ALIASES = {
    "html": "html",
    "css": "css",
    "javascript": "javascript",
    "js": "javascript",
    "accessibility": "accessibility",
    "a11y": "accessibility",
    "form": "forms",
    "forms": "forms",
    "export": "export",
}


def tutorial_tracks() -> dict[str, dict[str, Any]]:
    return {
        key: {"title": track["title"], "steps": [dict(step) for step in track["steps"]]}
        for key, track in TUTORIAL_TRACKS.items()
    }


def resolve_track(text: str) -> str | None:
    lowered = (text or "").lower()
    for keyword, track_id in _TRACK_ALIASES.items():
        if keyword in lowered:
            return track_id
    return None


def track_step_count(track_id: str) -> int:
    track = TUTORIAL_TRACKS.get(track_id)
    return len(track["steps"]) if track else 0
