from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IntentResult:
    action: str
    confidence: float
    text: str
    slots: dict[str, Any] = field(default_factory=dict)
    needs_clarification: bool = False
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "text": self.text,
            "slots": self.slots,
            "needs_clarification": self.needs_clarification,
            "message": self.message,
        }


@dataclass(frozen=True)
class IntentRule:
    action: str
    priority: int
    patterns: tuple[str, ...]
    confidence: float = 0.9
    slotter: Callable[[str], dict[str, Any]] | None = None


def _slot_after(command: str, words: tuple[str, ...], key: str) -> dict[str, Any]:
    lower = command.lower()
    for word in words:
        index = lower.find(word)
        if index != -1:
            value = command[index + len(word) :].strip(" :.-")
            if value:
                return {key: value}
    return {}


def _build_slots(command: str) -> dict[str, Any]:
    match = re.search(r"(?:build|make|create|generate|banao|bana do|website for|ke liye website)\s+(.+)", command, re.I)
    return {"prompt": match.group(1).strip()} if match else {"prompt": command}


def _page_slots(command: str) -> dict[str, Any]:
    lower = command.lower()
    if "contact" in lower:
        return {"page": "contact"}
    if "about" in lower:
        return {"page": "about"}
    if "home" in lower:
        return {"page": "home"}
    return _slot_after(command, ("add page", "go to page", "switch to page", "open page"), "page")


def _section_slots(command: str) -> dict[str, Any]:
    return _slot_after(command, ("add section", "insert section", "new section"), "section")


def _read_code_slots(command: str) -> dict[str, Any]:
    lower = command.lower()
    if "css" in lower or "style" in lower:
        target = "css"
    elif "javascript" in lower or "java script" in lower or re.search(r"\bjs\b", lower) or "script" in lower:
        target = "js"
    elif "html" in lower or "markup" in lower:
        target = "html"
    else:
        target = "all"
    return {"target": target}


def _design_slots(command: str) -> dict[str, Any]:
    lower = command.lower()
    if "futuristic" in lower:
        return {"preset": "futuristic"}
    if "animation" in lower or "animated" in lower:
        return {"preset": "animated"}
    return {"preset": "vibrant"}


def _snippet_slots(command: str) -> dict[str, Any]:
    match = re.search(
        r"\b(?:save|load|delete|remove)\s+(?:the\s+)?snippet\s*(?:as\s+|called\s+|named\s+)?(.+)",
        command,
        re.IGNORECASE,
    )
    if match:
        return {"snippet_name": match.group(1).strip()}
    return {}


def _named_slot(command: str) -> dict[str, Any]:
    match = re.search(r"\bbookmark\s+this(?:\s+issue)?\s+as\s+(.+)$", command, re.IGNORECASE)
    if match:
        return {"name": match.group(1).strip()}
    match = re.search(r"\b(?:as|called|named|macro|bookmark)\s+(.+)$", command, re.IGNORECASE)
    if match:
        return {"name": match.group(1).strip()}
    return {}


def _watchpoint_slots(command: str) -> dict[str, Any]:
    lower = command.lower()
    if "heading" in lower:
        return {"watchpoint": "heading_order"}
    if "alt" in lower or "image" in lower:
        return {"watchpoint": "image_alt"}
    if "button" in lower:
        return {"watchpoint": "button_label"}
    if "form" in lower or "input" in lower or "label" in lower:
        return {"watchpoint": "form_label"}
    if "contrast" in lower:
        return {"watchpoint": "contrast"}
    return {"watchpoint": "accessibility"}


def _tutorial_slots(command: str) -> dict[str, Any]:
    lower = command.lower()
    for keyword, track in (
        ("html", "html"),
        ("css", "css"),
        ("javascript", "javascript"),
        ("js", "javascript"),
        ("accessibility", "accessibility"),
        ("form", "forms"),
        ("export", "export"),
    ):
        if keyword in lower:
            return {"track": track}
    return {}


def _selector_query_slots(command: str) -> dict[str, Any]:
    return {"query": command.strip()}


def _bookmark_slots(command: str) -> dict[str, Any]:

    match = re.search(r"\bas\s+(.+)$", command, re.IGNORECASE)
    if match:
        return {"name": match.group(1).strip(" .:-")}
    match = re.search(r"\bbookmark\s+(?:this|the|current|that)?\s*(.+)$", command, re.IGNORECASE)
    if match and match.group(1).strip():
        return {"name": match.group(1).strip(" .:-")}
    return {}


_COMMAND_PHRASE_REPAIRS: tuple[tuple[str, str], ...] = (
    (r"\bexport\s+side\b", "export site"),
    (r"\bmake\s+webside\b", "make website"),
)

_COMMAND_TOKEN_REPAIRS: dict[str, str] = {
    "webside": "website",
    "wesbite": "website",
    "websit": "website",
    "wbsite": "website",
    "accessiblity": "accessibility",
    "accesibility": "accessibility",
    "accessibilty": "accessibility",
    "acessibility": "accessibility",
    "explane": "explain",
    "explian": "explain",
    "profeshnal": "professional",
    "profesional": "professional",
    "professionl": "professional",
    "cantact": "contact",
    "conatct": "contact",
    "naration": "narration",
    "nardation": "narration",
    "mapp": "map",
}

_TOKEN_REPAIR_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(token) for token in _COMMAND_TOKEN_REPAIRS) + r")\b",
    re.IGNORECASE,
)


def repair_command(text: str) -> str:
    if not text:
        return text
    repaired = text
    for pattern, replacement in _COMMAND_PHRASE_REPAIRS:
        repaired = re.sub(pattern, replacement, repaired, flags=re.IGNORECASE)
    if _TOKEN_REPAIR_PATTERN.search(repaired):
        repaired = _TOKEN_REPAIR_PATTERN.sub(lambda match: _COMMAND_TOKEN_REPAIRS[match.group(0).lower()], repaired)
    return repaired


RULES: tuple[IntentRule, ...] = (
    IntentRule("set_wake_word", 100, (r"\b(set|change)\s+wake\s+word\s+to\b",)),
    IntentRule(
        "help_guide",
        100,
        (
            r"^what\s+can\s+i\s+do\s+here\??$",
            r"^help$",
            r"\bshow\s+examples\b",
            r"\bwhat\s+can\s+codeup\s+web\s+do\b",
        ),
    ),
    IntentRule(
        "tutorial_start",
        100,
        (
            r"^start\s+tutorial$",
            r"^tutorial$",
            r"\bstart\s+(?:the\s+)?(?:html|css|javascript|accessibility|forms?|export)\s+tutorial\b",
            r"\bpracti[cs]e\s+(html|css|javascript|accessibility)\b",
        ),
        slotter=_tutorial_slots,
    ),
    IntentRule(
        "tutorial_control",
        100,
        (
            r"^continue$",
            r"^next$",
            r"^next\s+step$",
            r"^try\s+again$",
            r"^practi[cs]e\s+again$",
            r"^recap$",
            r"^hint$",
            r"^repeat$",
            r"^give\s+me\s+an\s+example$",
            r"^read\s+my\s+code$",
            r"^exit\s+tutorial$",
            r"^start\s+coding$",
        ),
    ),
    IntentRule(
        "guided_build_start",
        96,
        (
            r"\bstart\s+web\s+tutorial\b",
            r"\bbuild\s+my\s+first\s+website\b",
            r"\bbuild\s+(?:a\s+)?website\s+by\s+ear\b",
            r"\bguided\s+(?:website\s+)?build\b",
        ),
    ),
    IntentRule(
        "walkthrough_page",
        99,
        (
            r"\bwalk\s+me\s+through\b",
            r"\baudio\s+accessibility\s+walkthrough\b",
            r"\bread\s+the\s+page\s+structure\b",
        ),
    ),
    IntentRule(
        "walkthrough_keyboard_start",
        99,
        (r"\bstart\s+keyboard\s+journey\b",),
    ),
    IntentRule(
        "walkthrough_next_element",
        99,
        (r"\bnext\s+interactive\s+element\b",),
    ),
    IntentRule(
        "walkthrough_prev_element",
        99,
        (r"\bprevious\s+interactive\s+element\b",),
    ),
    IntentRule(
        "walkthrough_pause_issues",
        99,
        (
            r"\bpause\s+on\s+accessibility\s+issues\b",
            r"\bpause\s+when\s+heading\s+order\s+breaks\b",
            r"\bpause\s+when\s+(?:an?\s+)?image\s+has\s+no\s+alt\s+text\b",
            r"\bpause\s+when\s+a\s+button\s+has\s+no\s+label\b",
            r"\bpause\s+when\s+form\s+input\s+has\s+no\s+label\b",
            r"\bpause\s+when\s+contrast\s+is\s+low\b",
        ),
        slotter=_watchpoint_slots,
    ),
    IntentRule(
        "walkthrough_list_watchpoints",
        99,
        (r"\blist\s+accessibility\s+watchpoints\b",),
    ),
    IntentRule(
        "walkthrough_explain_issue",
        99,
        (
            r"\bexplain\s+first\s+issue\b",
            r"\bwhy\s+is\s+this\s+inaccessible\b",
            r"\bwhy\s+did\s+it\s+pause\b",
        ),
    ),
    IntentRule(
        "walkthrough_fix_issue",
        99,
        (r"\bfix\s+this\s+issue\b",),
    ),
    IntentRule(
        "walkthrough_compare",
        99,
        (r"\bcompare\s+accessibility\s+before\s+and\s+after\b",),
    ),
    IntentRule(
        "walkthrough_stop",
        99,
        (r"\bstop\s+walkthrough\b",),
    ),
    IntentRule("walkthrough_next_element", 99, (r"\bcontinue\s+walkthrough\b",)),
    IntentRule(
        "pause_voice",
        98,
        (
            r"\bpause\s+voice\b",
            r"\bstop\s+listening\b",
            r"\bvoice\s+off\b",
            r"\bstop\s+voice\b",
            r"\bawaaz\s+rok\b",
            r"\bruk\s+jao\b",
            r"\bvoice\s+band\s+karo\b",
            r"\bsunna\s+band\s+karo\b",
        ),
    ),
    IntentRule(
        "resume_voice",
        98,
        (
            r"\bresume\s+voice\b",
            r"\bvoice\s+on\b",
            r"\bstart\s+listening\b",
            r"\bphir\s+se\b",
            r"\bchalu\b",
            r"\bvoice\s+on\s+karo\b",
            r"\bdobara\s+sunna\s+shuru\s+karo\b",
        ),
    ),
    IntentRule(
        "stop_speaking",
        97,
        (r"\bstop\s+speaking\b", r"\bstop\s+everything\b", r"^cancel$", r"^stop$", r"\bquiet\b", r"\bchup\b"),
    ),
    IntentRule("set_voice_language", 96, (r"\bvoice\s+language\b", r"\bspeech\s+language\b", r"\bbhasha\b")),
    IntentRule("navigate_page", 90, (r"\b(next|previous)\s+(heading|section)\b", r"\bread\s+paragraph\s+\d+\b")),
    IntentRule("read_current_section", 89, (r"\bread\s+current\s+section\b", r"\bcurrent\s+section\s+read\b")),
    IntentRule("read_next_section", 89, (r"\bread\s+next\s+section\b", r"\bnext\s+section\b")),
    IntentRule(
        "step_narration",
        89,
        (
            r"\bstep\s+narration\b",
            r"\bnarrate\s+steps\b",
            r"\bwalk\s+me\s+through\b",
            r"\bhow\s+(?:does\s+)?(?:this\s+)?(?:code|website|project)\s+(?:work|run)s?\b",
            r"\bteach\s+me\s+this\s+website\b",
        ),
    ),
    IntentRule(
        "trainer_notes",
        91,
        (
            r"\bmake\s+trainer\s+notes\b",
            r"\btrainer\s+notes\b",
            r"\bteacher\s+notes\b",
            r"\btrainer\s+handoff\b",
            r"\blesson\s+notes(?:\s+for\s+(?:the\s+)?teacher)?\b",
            r"\bnotes?\s+for\s+(?:the\s+)?teacher\b",
        ),
    ),
    IntentRule(
        "student_recap",
        91,
        (
            r"\bwhat\s+did\s+i\s+learn(?:\s+today)?\b",
            r"\bsession\s+recap\b",
            r"\blearning\s+recap\b",
            r"\brecap\s+(?:my|the|this)\s+session\b",
        ),
    ),
    IntentRule(
        "screen_reader_prep",
        91,
        (
            r"\bprepare\s+(?:this\s+)?for\s+nvda\b",
            r"\bprepare\s+(?:this\s+)?for\s+(?:a\s+)?screen\s+reader\b",
            r"\bscreen\s+reader\s+summary\b",
            r"\bnvda\s+summary\b",
            r"^nvda$",
        ),
    ),
    IntentRule(
        "landmarks",
        91,
        (
            r"^landmarks$",
            r"\blist\s+landmarks\b",
            r"\bwebsite\s+landmarks\b",
            r"\bpage\s+landmarks\b",
            r"\bshow\s+landmarks\b",
            r"\blandmarks\b",
            r"^sections$",
            r"^show\s+sections$",
            r"\bshow\s+(?:me\s+)?(?:the\s+)?sections\b",
            r"\blist\s+sections\b",
            r"\bpage\s+sections\b",
        ),
    ),
    IntentRule(
        "runtime_teacher",
        92,
        (
            r"\bwhat\s+happens\s+when\s+(?:this|it|the\s+page)\s+runs?\b",
            r"\bruntime\s+teacher\b",
            r"\bwebsite\s+runtime\s+teacher\b",
            r"\bteach\s+me\s+how\s+this\s+website\s+runs?\b",
        ),
    ),
    IntentRule(
        "run_summary",
        92,
        (
            r"\brun\s+(?:this\s+)?website\b",
            r"\btest\s+(?:this\s+)?(?:website|site)\b",
            r"\brun\s+this\s+site\b",
            r"\bcheck\s+if\s+this\s+website\s+works\b",
        ),
    ),
    IntentRule(
        "selector_explainer",
        92,
        (
            r"\bwhat\s+css\s+affects?\b",
            r"\bwhich\s+css\s+affects?\b",
            r"\bexplain\s+css\s+for\b",
            r"\b(?:find\s+)?unused\s+css\b",
            r"\bwhich\s+html\s+uses\b",
        ),
        slotter=_selector_query_slots,
    ),
    IntentRule(
        "pilot_report",
        91,
        (
            r"\bmake\s+(?:a\s+)?pilot\s+report\b",
            r"\bpilot\s+report\b",
            r"\bmake\s+(?:a\s+)?trainer\s+report\b",
            r"\btrainer\s+report\b",
            r"\bsummari[sz]e\s+(?:this\s+)?session\b",
            r"\bwhat\s+did\s+the\s+student\s+learn\b",
        ),
    ),
    IntentRule(
        "readiness_score",
        92,
        (
            r"\bis\s+this\s+ready\s+to\s+share\b",
            r"\bwebsite\s+readiness\b",
            r"\breadiness\s+score\b",
            r"\bproject\s+score\b",
            r"\bis\s+this\s+website\s+good\b",
            r"\bshould\s+i\s+share\s+this(?:\s+website)?\b",
            r"\bcan\s+i\s+export\s+this\b",
            r"\bteacher\s+check\b",
            r"\bnab\s+readiness\s+check\b",
            r"\breadiness\s+check\b",
        ),
    ),
    IntentRule(
        "debug_fix",
        91,
        (
            r"\bfix\s+website\s+error\b",
            r"\bfix\s+(?:the\s+)?javascript\s+error\b",
            r"\bfix\s+js\s+error\b",
        ),
    ),
    IntentRule(
        "debug_website",
        90,
        (
            r"\bdebug\b",
            r"\bwhy\s+is\s+this\s+website\s+broken\b",
            r"\bexplain\s+website\s+error\b",
            r"\bcheck\s+console\s+errors\b",
            r"\bdebug\s+this\s+like\s+a\s+teacher\b",
            r"\bwhy\s+is\s+my\s+button\s+not\s+working\b",
            r"\bcheck\s+javascript\s+connections\b",
            r"\bexplain\s+errors\b",
        ),
    ),
    IntentRule(
        "screen_reader_tour",
        90,
        (
            r"\bscreen\s+reader\s+tour\b",
            r"\breading\s+order\s+tour\b",
            r"\bscreen\s+reader\s+reading\s+order\b",
            r"\bhow\s+would\s+a\s+screen\s+reader\s+read\s+this\b",
            r"\bnvda\s+tour\b",
            r"\bjaws\s+tour\b",
        ),
    ),
    IntentRule(
        "keyboard_test",
        90,
        (
            r"\btest\s+keyboard\s+navigation\b",
            r"\bkeyboard\s+navigation\s+test\b",
            r"\bkeyboard\s+test\b",
            r"\btab\s+order\b",
            r"\btest\s+tab\s+order\b",
            r"\bcan\s+keyboard\s+users\s+use\s+this\b",
            r"\bfocus\s+order\b",
        ),
    ),
    IntentRule(
        "visual_description",
        90,
        (
            r"\bdescribe\s+the\s+design\b",
            r"\bdescribe\s+the\s+website\s+visually\b",
            r"\bwhat\s+does\s+(?:the\s+)?website\s+look\s+like\b",
            r"\bvisual\s+description\b",
            r"\bdescribe\s+layout\b",
            r"\bdescribe\s+(?:the\s+)?colou?rs?\b",
        ),
    ),
    IntentRule(
        "version_history",
        90,
        (
            r"\bshow\s+history\b",
            r"\bversion\s+history\b",
            r"\bshow\s+version\s+history\b",
        ),
    ),
    IntentRule(
        "teacher_review",
        86,
        (
            r"\bimprove\s+like\s+a\s+teacher\b",
            r"\breview\s+like\s+a\s+teacher\b",
            r"\bsuggest\s+improvements\b",
            r"\bteacher\s+review\b",
            r"\bimprove\s+this\s+project\b",
        ),
    ),
    IntentRule(
        "learning_notes",
        89,
        (
            r"\blearning\s+notes\b",
            r"\bconcepts?\s+(?:used|are\s+in\s+this\s+project)\b",
        ),
    ),
    IntentRule(
        "accessibility_map",
        89,
        (
            r"\baccessibility\s+map\b",
            r"\bexplain\s+accessibility\b",
            r"\baccessibility\s+explanation\b",
            r"\baccessibility\s+notes\b",
        ),
    ),
    IntentRule(
        "describe_preview",
        89,
        (
            r"\bdescribe\s+preview\b",
            r"\bdescribe\s+output\b",
            r"\bwhat\s+will\s+(?:the\s+)?user\s+see\b",
        ),
    ),
    IntentRule(
        "review_project",
        89,
        (
            r"\breview\s+project\b",
            r"\breview\s+this\s+project\b",
            r"\breview\s+this\s+code\b",
            r"\bwhat\s+should\s+i\s+improve\b",
        ),
    ),
    IntentRule(
        "project_summary",
        89,
        (r"\bproject\s+summary\b", r"\bwhat\s+did\s+i\s+build\b", r"\bwhat\s+project\s+type\b"),
    ),
    IntentRule(
        "file_explanation",
        88,
        (
            r"\bexplain\s+(?:the\s+)?(?:index\.html|html\s+file|style\.css|css|style\s+file|script\.js|javascript|java script|js|script\s+file)\b",
            r"\bwhat\s+does\s+(?:the\s+)?(?:index\.html|html\s+file|style\.css|css|script\.js|javascript|java script|js)\b",
        ),
        slotter=_read_code_slots,
    ),
    IntentRule(
        "code_map",
        88,
        (
            r"\bcode\s+map\b",
            r"\bwebsite\s+map\b",
            r"\bproject\s+map\b",
            r"\bmap\s+of\s+the\s+code\b",
            r"\bmap\s+the\s+code\b",
            r"\bmap\s+this\s+website\b",
            r"\bexplain\s+(?:the\s+)?structure\b",
            r"\bsummari[sz]e\s+structure\b",
            r"\bwhat\s+files\s+are\s+here\b",
            r"\bwhat\s+sections\s+are\s+(?:on|in)\s+this\s+page\b",
            r"\bwhat\s+is\s+inside\s+the\s+hero\s+section\b",
            r"\bwhat\s+comes\s+after\s+the\s+navigation\b",
            r"\blist\s+all\s+buttons\b",
            r"\blist\s+all\s+forms\b",
            r"\bwhat\s+css\s+styles\s+the\s+hero\s+section\b",
            r"\bwhat\s+javascript\s+controls\s+the\s+dark\s+mode\s+button\b",
            r"\bhow\s+deeply\s+nested\s+am\s+i\b",
            r"\bread\s+the\s+page\s+structure\b",
        ),
    ),
    IntentRule("darken_theme", 87, (r"\bdarken\b", r"\bdark\s+theme\b", r"\bdark\s+mode\b", r"\bnight\s+mode\b")),
    IntentRule("lighten_theme", 87, (r"\blighten\b", r"\blighter\s+theme\b", r"\blight\s+theme\b")),
    IntentRule(
        "read_code",
        87,
        (r"\bread\s+(the\s+)?(code|html|css|javascript|java script|js|script)\b",),
        slotter=_read_code_slots,
    ),
    IntentRule(
        "analyze_code",
        86,
        (r"\banaly[sz]e\s+(the\s+)?code\b", r"\bfind\s+problems\b", r"\bcheck\s+the\s+code\b"),
    ),
    IntentRule(
        "explain_javascript",
        86,
        (r"\bexplain\s+(the\s+)?(javascript|java script|js|script)\b",),
    ),
    IntentRule(
        "design_preset",
        85,
        (
            r"\bmore\s+beautiful\b",
            r"\bmore\s+colo[u]?rful\b",
            r"\bmore\s+futuristic\b",
            r"\bfuturistic\b",
            r"\badd\s+animations?\b",
            r"\bimprove\s+the\s+design\b",
            r"\bmake\s+it\s+pop\b",
        ),
        slotter=_design_slots,
    ),
    IntentRule("add_contact_section", 85, (r"\badd\s+(a\s+)?contact\s+(section|form)\b",)),
    IntentRule(
        "add_js_interactivity",
        85,
        (r"\badd\s+(javascript|java script|js)\s+interactivity\b", r"\badd\s+interactivity\b"),
    ),
    IntentRule(
        "edit_css",
        84,
        (
            r"\bhigh\s+contrast\b",
            r"\b(change|set|make|turn|use)\b.*\b(background|font|text color|spacing|rounded|bold|bigger|smaller)\b",
            r"\b(center|align)\s+(the\s+)?(text|heading|section|button|content)\b",
            r"\b(text|heading|section|button|content)\b.*\bcenter\b",
        ),
    ),
    IntentRule("announce_contrast", 82, (r"\bcontrast\b",)),
    IntentRule(
        "explain_concept",
        81,
        (r"\bwhat\s+is\s+a\s+div\b", r"\baria-label\b", r"\bwhat\s+does\b", r"\bexplain\s+concept\b"),
    ),
    IntentRule(
        "undo_version",
        80,
        (
            r"\bgo\s+back\b",
            r"^undo\b",
            r"\bundo\s+last\s+change\b",
            r"\brestore\s+previous\s+version\b",
            r"\brestore\s+the\s+previous\s+version\b",
        ),
    ),
    IntentRule(
        "review_changes",
        79,
        (
            r"\bwhat\s+changed\b",
            r"\breplay\s+change\b",
            r"\breplay\s+(?:the\s+|my\s+)?changes?\b",
            r"\bcompare\s+versions\b",
            r"\breview\s+changes\b",
            r"\bcompare\s+before\s+and\s+after\b",
            r"\bread\s+before\s+and\s+after\b",
            r"\bexplain\s+this\s+change\b",
            r"\bis\s+this\s+risky\b",
            r"\bchange\s+risk\b",
            r"\breplay\s+my\s+mistake\b",
            r"\bwhy\s+does\s+the\s+fixed\s+version\s+work\b",
            r"\bshow\s+changed\s+lines\b",
            r"\bread\s+only\s+what\s+changed\b",
            r"\bcompare\s+preview\s+changes\b",
            r"\bcompare\s+code\s+changes\b",
        ),
    ),
    IntentRule(
        "explain_errors",
        79,
        (
            r"\bexplain\s+simply\b",
            r"\bexplain\s+this\s+error\b",
            r"\bwhy\s+is\s+this\s+broken\b",
            r"\bfix\s+and\s+explain\b",
        ),
    ),
    IntentRule(
        "breadcrumb",
        79,
        (r"\bwhere\s+am\s+i\b", r"\bread\s+breadcrumb\b", r"\bwhat\s+am\s+i\s+editing\b"),
    ),
    IntentRule(
        "save_macro",
        79,
        (r"\bremember\s+this\s+as\b", r"\bsave\s+this\s+command\s+as\b"),
        slotter=_named_slot,
    ),
    IntentRule("run_macro", 79, (r"\b(use|run)\s+macro\b",), slotter=_named_slot),
    IntentRule("list_macros", 79, (r"\blist\s+macros\b",)),
    IntentRule("delete_macro", 79, (r"\bdelete\s+macro\b",), slotter=_named_slot),
    IntentRule(
        "save_bookmark",
        79,
        (
            r"\bbookmark\s+(?:this|the|current|that)\b",
            r"\bbookmark\b[^?]*\bas\b",
        ),
        slotter=_bookmark_slots,
    ),
    IntentRule(
        "read_bookmark",
        79,
        (r"\bread\s+from\s+bookmark\b", r"\bgo\s+to\s+bookmark\b", r"\bopen\s+bookmark\b"),
        slotter=_bookmark_slots,
    ),
    IntentRule("list_bookmarks", 79, (r"\blist\s+bookmarks\b",)),
    IntentRule("delete_bookmark", 79, (r"\bdelete\s+bookmark\b",), slotter=_named_slot),
    IntentRule(
        "restore_work",
        79,
        (r"\brestore\s+my\s+last\s+work\b", r"\bwhat\s+did\s+i\s+last\s+work\s+on\b"),
    ),
    IntentRule("create_multipage_site", 78, (r"\bmulti[- ]?page\b", r"\bmultiple\s+page\b", r"\bhomepage\s+plus\b")),
    IntentRule("add_contact_page", 77, (r"\badd\s+(a\s+)?contact\s+page\b",), slotter=_page_slots),
    IntentRule("switch_page", 76, (r"\b(go|switch|open)\s+to\s+page\b",), slotter=_page_slots),
    IntentRule("add_section", 75, (r"\b(add|insert|new)\s+section\b",), slotter=_section_slots),
    IntentRule("use_template", 74, (r"\btemplate\b",)),
    IntentRule(
        "apply_audit_fixes",
        73,
        (
            r"\bapply\s+(all\s+)?(safe\s+)?fixes\b",
            r"\bfix\s+accessibility\b",
            r"\bmake\s+it\s+accessible\b",
            r"\bfix\s+(the\s+)?code\b",
            r"\bautofix\b",
        ),
    ),
    IntentRule(
        "apply_review",
        72,
        (
            r"\badd\s+that\b",
            r"\bapply\s+that\b",
            r"\bfix\s+missing\b",
            r"\buse\s+your\s+suggestions\b",
            r"\bwoh\s+add\s+karo\b",
        ),
    ),
    IntentRule(
        "review_site",
        71,
        (
            r"\bwhat\s+do\s+you\s+think\b",
            r"\bmissing\b",
            r"\breview\b",
            r"\bfeedback\b",
            r"\bkaisi\s+dikhti\b",
            r"\bkya\s+kami\b",
        ),
    ),
    IntentRule(
        "preview_site",
        70,
        (
            r"\bpreview\b",
            r"\bshow\s+(?:me\s+)?(?:the\s+)?website\b",
            r"\brun\s+website\b",
            r"\bdikhao\b",
            r"\bpage\s+preview\s+karo\b",
            r"\bwebsite\s+dikhao\b",
        ),
    ),
    IntentRule(
        "audit_site",
        69,
        (
            r"\baudit\b",
            r"\baccessibility\s+score\b",
            r"\bcheck\s+accessibility\b",
            r"\baccessibility\s+issues?\s+check\s+karo\b",
            r"\bmissing\s+alt\s+text\s+fix\s+karo\b",
        ),
    ),
    IntentRule(
        "outline_site",
        68,
        (
            r"\boutline\b",
            r"\bpage\s+structure\b",
            r"\bpage\s+ka\s+structure\s+samjhao\b",
            r"\bwebsite\s+ka\s+layout\s+batao\b",
        ),
    ),
    IntentRule("export_site", 67, (r"\bexport\b", r"\bdownload\b", r"\bzip\b")),
    IntentRule(
        "reset_session",
        66,
        (
            r"\breset\s+session\b",
            r"^reset$",
            r"\beditor\s+clear\s+karo\b",
            r"\bpage\s+clear\s+karo\b",
            r"\bnaya\s+page\s+shuru\s+karo\b",
            r"\bclear\s+editor\b",
            r"^start\s+over$",
            r"\bstart\s+over\b",
        ),
    ),
    IntentRule(
        "explain_site", 65, (r"\bexplain\b", r"\bdescribe\b", r"\bsummari[sz]e\b", r"\blooks\b", r"\bsamjhao\b")
    ),
    IntentRule(
        "sonify_site",
        64,
        (
            r"\bsonify\b",
            r"\bsound\b",
            r"\baudio\s+structure\b",
            r"\bsunao\b",
            r"\bpage\s+structure\s+sonify\s+karo\b",
            r"\blayout\s+ka\s+audio\s+structure\s+sunao\b",
        ),
    ),
    IntentRule("polish_html", 63, (r"\bpolish\b", r"\bfix\s+html\b", r"\bimprove\b", r"\btheek\b")),
    IntentRule(
        "edit_website",
        64,
        (
            r"\bmake\s+it\s+more\s+professional\b",
            r"\bmake\s+it\s+simpler\b",
            r"\bmake\s+(?:the\s+)?text\s+easier\s+to\s+read\b",
            r"\badd\s+(?:an?\s+)?about\s+section\b",
            r"\badd\s+(?:an?\s+)?section\s+about\b",
            r"\badd\s+(?:an?\s+)?section\s+for\b",
            r"\bchange\s+(?:the\s+)?(?:website\s+)?(?:name|title)\s+to\b",
            r"\bmake\s+(?:the\s+)?title\s+shorter\b",
            r"\bimprove\s+(?:the\s+)?navigation\b",
            r"\bmake\s+(?:the\s+)?buttons?\s+clearer\b",
            r"\badd\s+(?:a\s+)?button\b",
            r"\badd\s+(?:a\s+)?footer\b",
            r"\badd\s+score\s+tracking\b",
            r"\bchange\s+(?:the\s+)?background\s+colou?r\b",
            r"\badd\s+comments?\b",
            r"\bcomment\s+(?:the\s+)?code\b",
            r"\bmake\s+(?:it|the\s+javascript|the\s+java\s+script|the\s+js)\s+use\s+(?:a\s+)?function\b",
            r"\buse\s+(?:a\s+)?function\b",
        ),
    ),
    IntentRule(
        "save_snippet",
        62,
        (r"\bsave\b.*\bsnippet\b", r"\bsnippet\s+save\s+karo\b"),
        slotter=_snippet_slots,
    ),
    IntentRule(
        "list_snippets",
        62,
        (r"\b(show|list)\b.*\bsnippets?\b", r"\b(mere|mera)\s+snippets?\b", r"\bsnippets?\s+(dikhao|batao)\b"),
    ),
    IntentRule(
        "load_snippet",
        62,
        (r"\bload\b.*\bsnippet\b", r"\bsnippet\s+load\s+karo\b"),
        slotter=_snippet_slots,
    ),
    IntentRule(
        "delete_snippet",
        62,
        (r"\b(delete|remove)\b.*\bsnippet\b", r"\bsnippet\s+(delete|hatao)\b"),
        slotter=_snippet_slots,
    ),
    IntentRule(
        "build_site",
        60,
        (
            r"\b(build|make|create|generate)\b.*\b(website|site|page|webpage|app|project|quiz|calculator|todo|to-do|flashcard|poll|dashboard|timetable|tracker)\b",
            r"\b(website|site|page|webpage|app|project|quiz|calculator|todo|to-do|flashcard|poll|dashboard|timetable|tracker)\s+(?:for|about)\b",
            r"\b(banao|bana do|banaiye|banaye|banaao)\b",
        ),
        slotter=_build_slots,
    ),
)


def _route_python_intent(command: str) -> IntentResult | None:
    lower = command.lower().strip()
    if "website" in lower or "site" in lower:
        return None
    state_patterns: tuple[tuple[str, str], ...] = (
        (r"^next\s+step$", "next"),
        (r"^previous\s+step$", "previous"),
        (r"^go\s+back\s+one\s+step$", "previous"),
        (r"^explain\s+this\s+step$", "current"),
        (r"^what\s+changed\s+in\s+python$", "what_changed"),
        (r"^where\s+am\s+i\s+in\s+python$", "where"),
        (r"^repeat\s+that$", "repeat"),
        (r"^why\s+did\s+[a-zA-Z_]\w*\s+change$", "why_variable_change"),
        (r"^why\s+did\s+the\s+condition\s+pass$", "condition_pass"),
        (r"^why\s+did\s+the\s+condition\s+fail$", "condition_fail"),
        (r"^explain\s+the\s+loop$", "loop"),
        (r"^step\s+into(?:\s+function)?$", "step_into"),
        (r"^step\s+out$", "step_out"),
        (r"^leave\s+function$", "step_out"),
        (r"^what\s+function\s+am\s+i\s+in$", "where_function"),
        (r"^what\s+arguments\s+were\s+passed$", "arguments"),
        (r"^what\s+are\s+the\s+parameters$", "parameters"),
        (r"^what\s+did\s+it\s+return$", "return"),
        (r"^where\s+does\s+it\s+go\s+back$", "go_back"),
        (r"^explain\s+this\s+function(?:\s+call)?$", "function"),
        (r"^why\s+did\s+this\s+function\s+return\s+this$", "why_function_return"),
    )
    for pattern, action in state_patterns:
        if re.search(pattern, lower):
            slots: dict[str, Any] = {"state_action": action}
            match = re.search(r"^why\s+did\s+([a-zA-Z_]\w*)\s+change$", lower)
            if match:
                slots["variable"] = match.group(1)
            return IntentResult("python_state_watch", 0.98, command, slots)
    if re.search(r"\b(run|execute)\s+(?:this\s+)?(?:python\s+)?code\b", lower):
        return IntentResult("python_run", 0.98, command)
    if re.search(r"\bteach\s+me\s+(?:this\s+)?code\b", lower):
        return IntentResult("python_teach", 0.98, command)
    if re.search(r"\baudio\s+code\s+map\b", lower):
        return IntentResult("python_audio_code_map", 0.98, command)
    match = re.search(r"\bwatch\s+variable\s+([a-zA-Z_]\w*)\b", lower)
    if match:
        return IntentResult("python_watch_variable", 0.98, command, {"variable": match.group(1)})
    match = re.search(r"\bbreak\s+when\s+(.+)$", command, re.IGNORECASE)
    if match:
        return IntentResult("python_conditional_breakpoint", 0.98, command, {"condition": match.group(1).strip()})
    if re.search(r"\bconditional\s+breakpoint\b", lower):
        return IntentResult("python_conditional_breakpoint", 0.98, command, {"condition": command})
    return None


def route_intent(text: str) -> IntentResult:
    command = repair_command((text or "").strip())
    if not command:
        return IntentResult("unknown", 0.0, command, needs_clarification=True, message="No command heard")
    python_intent = _route_python_intent(command)
    if python_intent is not None:
        return python_intent

    candidates: list[IntentResult] = []
    for rule in RULES:
        if any(re.search(pattern, command, re.IGNORECASE) for pattern in rule.patterns):
            slots = rule.slotter(command) if rule.slotter else {}
            candidates.append(IntentResult(rule.action, rule.confidence + rule.priority / 1000, command, slots))

    if not candidates:
        return IntentResult("chat", 0.35, command)

    candidates.sort(key=lambda item: item.confidence, reverse=True)
    best = candidates[0]
    if len(candidates) > 1 and abs(best.confidence - candidates[1].confidence) < 0.001:
        return IntentResult(
            best.action,
            best.confidence,
            command,
            best.slots,
            needs_clarification=True,
            message=f"I heard more than one possible action: {best.action} or {candidates[1].action}.",
        )
    return best
