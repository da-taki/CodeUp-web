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
        (r"^start\s+tutorial$", r"^tutorial$", r"\bpracti[cs]e\s+(html|css|javascript|accessibility)\b"),
    ),
    IntentRule(
        "tutorial_control",
        100,
        (
            r"^continue$",
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
        "code_map",
        88,
        (
            r"\bcode\s+map\b",
            r"\bmap\s+of\s+the\s+code\b",
            r"\bmap\s+the\s+code\b",
            r"\bmap\s+this\s+website\b",
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
    IntentRule("undo_version", 80, (r"\bgo\s+back\b", r"^undo\b")),
    IntentRule(
        "review_changes",
        79,
        (
            r"\bwhat\s+changed\b",
            r"\bcompare\s+versions\b",
            r"\breview\s+changes\b",
            r"\bcompare\s+before\s+and\s+after\b",
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
        (r"\bbookmark\s+this\b", r"\bbookmark\s+this\s+issue\b"),
        slotter=_named_slot,
    ),
    IntentRule("read_bookmark", 79, (r"\bread\s+from\s+bookmark\b",), slotter=_named_slot),
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
            r"\bshow\s+website\b",
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
            r"\badd\s+(?:a\s+)?footer\b",
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
            r"\b(build|make|create|generate)\b.*\b(website|site|page|webpage)\b",
            r"\b(website|site|page|webpage)\s+for\b",
            r"\b(banao|bana do|banaiye|banaye|banaao)\b",
        ),
        slotter=_build_slots,
    ),
)


def route_intent(text: str) -> IntentResult:
    command = (text or "").strip()
    if not command:
        return IntentResult("unknown", 0.0, command, needs_clarification=True, message="No command heard")

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
