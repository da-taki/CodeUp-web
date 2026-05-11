"""
Smart Intent Parser for Voice Commands

Converts natural language voice input into structured intents and slots.
This replaces simple string matching with a robust grammar-based system.

Examples:
    "go to line fifteen"      -> {intent: "goto_line",      slots: {line_number: 15}}
    "read function analyze"   -> {intent: "read_function",  slots: {function_name: "analyze"}}
    "find class Parser"       -> {intent: "find_class",     slots: {class_name: "Parser"}}
    "jump to error"           -> {intent: "locate_error",   slots: {}}

Supported spoken numbers: zero–nineteen, tens (twenty, thirty … ninety), and
two-word compounds such as "twenty five" (→ 25), "forty two" (→ 42).
"""

import re
import threading
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Spoken-number vocabulary
# ---------------------------------------------------------------------------

_ONES: Dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS: Dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

# Hindi numbers 0-50. Hindi doesn't decompose into tens+ones the way English
# does ("twenty five" → 20+5), each number is its own word, so we list them
# directly. We cap at 50 because line numbers above that are rare in voice
# commands and the vocabulary gets unwieldy fast.
_HINDI_NUMBERS: Dict[str, int] = {
    "शून्य": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "पन्द्रह": 15,
    "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20,
    "इक्कीस": 21, "बाईस": 22, "तेईस": 23, "चौबीस": 24, "पच्चीस": 25,
    "छब्बीस": 26, "सत्ताईस": 27, "अट्ठाईस": 28, "उनतीस": 29, "तीस": 30,
    "इकतीस": 31, "बत्तीस": 32, "तैंतीस": 33, "चौंतीस": 34, "पैंतीस": 35,
    "छत्तीस": 36, "सैंतीस": 37, "अड़तीस": 38, "उनतालीस": 39, "चालीस": 40,
    "इकतालीस": 41, "बयालीस": 42, "तैंतालीस": 43, "चौवालीस": 44, "पैंतालीस": 45,
    "छियालीस": 46, "सैंतालीस": 47, "अड़तालीस": 48, "उनचास": 49, "पचास": 50,
    "इक्यावन": 51, "बावन": 52, "तिरपन": 53, "चौवन": 54, "पचपन": 55,
    "छप्पन": 56, "सत्तावन": 57, "अट्ठावन": 58, "उनसठ": 59, "साठ": 60,
    "इकसठ": 61, "बासठ": 62, "तिरसठ": 63, "चौंसठ": 64, "पैंसठ": 65,
    "छियासठ": 66, "सड़सठ": 67, "अड़सठ": 68, "उनहत्तर": 69, "सत्तर": 70,
    "इकहत्तर": 71, "बहत्तर": 72, "तिहत्तर": 73, "चौहत्तर": 74, "पचहत्तर": 75,
    "छिहत्तर": 76, "सतहत्तर": 77, "अठहत्तर": 78, "उनासी": 79, "अस्सी": 80,
    "इक्यासी": 81, "बयासी": 82, "तिरासी": 83, "चौरासी": 84, "पचासी": 85,
    "छियासी": 86, "सतासी": 87, "अट्ठासी": 88, "नवासी": 89, "नब्बे": 90,
    "इक्यानवे": 91, "बानवे": 92, "तिरानवे": 93, "चौरानवे": 94, "पचानवे": 95,
    "छियानवे": 96, "सत्तानवे": 97, "अट्ठानवे": 98, "निन्यानवे": 99, "सौ": 100,
}

# "hundred" and "thousand" appear here as standalone tokens but are also
# handled in compound parsing in IntentParser._word_to_number.
WORD_TO_NUMBER: Dict[str, int] = {
    **_ONES, **_TENS, **_HINDI_NUMBERS,
    "hundred": 100, "thousand": 1000,
}

class IntentParser:
    """Parse voice commands into structured intents and slots."""

    # -----------------------------------------------------------------------
    # Navigation patterns
    # -----------------------------------------------------------------------

    GOTO_LINE_PATTERNS = [
        r"(?:go|jump|navigate|move)\s+to\s+line\s+([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"(?:go|jump|navigate|move)\s+to\s+line\s+(\w+)",
        # Hindi: "लाइन पंद्रह पर जाओ" / "line 15 पर जाओ"
        r"(?:लाइन|line)\s+(\S+)\s+(?:पर\s+)?(?:जाओ|जाइए|चलो)",
    ]

    READ_LINE_PATTERNS = [
        r"read\s+(?:the\s+)?line\s+([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"read\s+(?:the\s+)?line\s+(\w+)",
        # Hindi: "लाइन पांच पढ़ो"
        r"(?:लाइन|line)\s+(\S+)\s+(?:को\s+)?(?:पढ़ो|पढ़िए|बोलो|सुनाओ)",
    ]

    READ_FUNCTION_PATTERNS = [
        r"read\s+(?:the\s+)?function\s+(\w+)",
    ]

    FIND_CLASS_PATTERNS = [
        r"(?:find|locate)\s+class\s+(\w+)",
        r"(?:go\s+)?to\s+class\s+(\w+)",
    ]

    FIND_FUNCTION_PATTERNS = [
        r"(?:find|locate)\s+function\s+(\w+)",
        r"(?:go\s+)?to\s+function\s+(\w+)",
    ]

    # -----------------------------------------------------------------------
    # Execution patterns
    RUN_PATTERNS = [
        # Core verbs
        r"^run\s*(?:code|program|it|this|that)?$",
        r"^execute\s*(?:code|program|it|this|that)?$",
        r"^start\s*(?:code|program|it|this|that)?$",
        r"^launch\s*(?:code|program|it|this|that)?$",
        r"^play\s*(?:code|program|it|this|that)?$",
        r"^go\s*(?:now)?$",
        # Casual phrasings — explicit terminators so "do it yourself" doesn't fire
        r"^let'?s?\s+(?:run|go|try)\s*(?:it|this|that)?\.?$",
        r"^try\s+(?:it|this|that)\.?$",
        r"^do\s+it\.?$",
        r"^make\s+it\s+(?:go|run)\.?$",
        r"^see\s+(?:what|if)\s+(?:happens|it\s+does|it\s+works)\.?$",
        # Hindi
        r"^(?:कोड\s+)?(?:चलाओ|चलाइए|चलाइये)$",
        r"^रन\s*(?:करो|कीजिए|कीजिये)?$",
        r"^शुरू\s+करो$",
        r"^देखो\s+क्या\s+होता\s+है$",
    ]


    ANALYZE_DEEP_PATTERNS = [
        r"^analyze\s+deeper$",
        r"^(?:go\s+)?deeper$",
        r"^more\s+detail(?:s)?$",
        r"^line\s+by\s+line$",
        r"^explain\s+(?:in\s+)?more\s+detail$",
        r"^गहराई\s+से\s+(?:analyze|समझाओ)$",
        r"^और\s+detail$",
    ]

    ANALYZE_PATTERNS = [
        r"^analyze\s*(?:(?:the\s+)?code)?$",
        r"^analyse\s*(?:(?:the\s+)?code)?$",
        r"^(?:check|review|explain)\s+(?:the\s+)?code$",
        # Hindi: "कोड का विश्लेषण करो" / "कोड समझाओ"
        r"^(?:कोड\s+)?(?:का\s+)?विश्लेषण\s*(?:करो|कीजिए)?$",
        r"^कोड\s+(?:को\s+)?(?:समझाओ|समझाइए|जांचो)$",
    ]

    FIX_PATTERNS = [
        r"^fix\s*(?:(?:my\s+|this\s+|the\s+)?(?:code|it|bug|error))?$",
        r"^auto\s*fix$",
        r"^repair\s+(?:my\s+|this\s+|the\s+)?code$",
        r"^correct\s+(?:my\s+|this\s+|the\s+)?code$",
        r"^debug\s+(?:my\s+|this\s+|the\s+)?code$",
        r"^make\s+it\s+work$",
        r"^what'?s?\s+wrong$",
        r"^why\s+(?:doesn'?t|isn'?t)\s+(?:it|this)\s+work(?:ing)?$",
        # Hindi
        r"^(?:कोड|गलती|error|bug)\s+(?:को\s+)?ठीक\s*(?:करो|कीजिए|कीजिये)?$",
        r"^सही\s+करो$",
        r"^क्या\s+गलत\s+है$",
        r"^काम\s+क्यों\s+नहीं\s+कर\s+रहा$",
    ]

    ADVISE_PATTERNS = [
        r"^advise(?:\s+on\s+(?:the\s+)?code)?$",
        r"^(?:give\s+)?advice(?:\s+on\s+(?:the\s+)?code)?$",
        r"how\s+can\s+i\s+improve\s+(?:this\s+)?code",
        r"what\s+features\s+can\s+i\s+add",
        r"^improve\s+(?:my\s+)?code$",
    ]

    SPEAK_OUTPUT_PATTERNS = [
        r"^(?:speak|read|say)\s+(?:the\s+)?output$",
    ]

    SHOW_STRUCTURE_PATTERNS = [
        r"^(?:show|display|list)\s+(?:code\s+)?structure$",
        r"^show\s+(?:code\s+)?map$",
        r"^structure\s+panel$",
    ]

    # -----------------------------------------------------------------------
    # Sonification patterns
    # -----------------------------------------------------------------------

    SONIFY_FUNCTION_PATTERNS = [
        r"sonify\s+(?:the\s+)?function\s+(\w+)",
    ]

    SONIFY_CLASS_PATTERNS = [
        r"sonify\s+(?:the\s+)?class\s+(\w+)",
    ]

    SONIFY_BLOCK_PATTERNS = [
        r"^sonify(?:\s+(?:block|current\s+block|this|this\s+block|code))?$",
        r"^(?:audio|hear|play|sound\s+out)\s+(?:code\s+)?(?:structure|block)?$",
        r"^play\s+(?:the\s+)?code$",
        r"^make\s+(?:it\s+)?sing$",
        r"^read\s+(?:current\s+)?line$",
        r"^read\s+this\s+line$",
        r"^what\s+(?:does\s+)?this\s+line\s+(?:say|do)$",
    ]

    # -----------------------------------------------------------------------
    # Error patterns
    # -----------------------------------------------------------------------

    ERROR_PATTERNS = [
        r"(?:find|locate|go\s+to|jump\s+to)\s+(?:the\s+)?error",
        r"where\s+is\s+(?:the\s+)?error",
        r"next\s+error",
    ]

    DESCRIBE_LINE_PATTERNS = [
        r"describe\s+(?:the\s+)?line\s+([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"describe\s+(?:the\s+)?line\s+(\w+)",
        r"what\s+is\s+on\s+line\s+([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"what\s+is\s+on\s+line\s+(\w+)",
    ]

    CLEAR_EDITOR_PATTERNS = [
        r"^(?:clear|reset)\s+(?:editor|code|file|the\s+editor)$",
        # Hindi: "एडिटर साफ करो" / "कोड हटाओ"
        r"^(?:एडिटर|editor|कोड|code)\s+(?:को\s+)?(?:साफ|खाली|reset)\s*(?:करो|कीजिए)?$",
        r"^(?:कोड|code)\s+(?:को\s+)?(?:हटाओ|मिटाओ)$",
    ]

    SET_COLOR_MODE_PATTERNS = [
        r"^(?:turn\s+on|enable|activate|use|set|toggle)\s+(protanopia|deuteranopia|tritanopia|high\s*contrast|red\s*blind|green\s*blind|blue\s*blind|normal|default|standard)\s*(?:mode|colors?)?$",
        r"^(?:switch\s+to|change\s+to)\s+(protanopia|deuteranopia|tritanopia|high\s*contrast|red\s*blind|green\s*blind|blue\s*blind|normal|default|standard)\s*(?:mode|colors?)?$",
        r"^(protanopia|deuteranopia|tritanopia|high\s*contrast|red\s*blind|green\s*blind|blue\s*blind)\s+mode$",
        r"^(?:turn\s+off|disable|reset)\s+(?:color\s+(?:blind\s+)?|colour\s+(?:blind\s+)?)?mode$",
    ]

    DELETE_LINE_PATTERNS = [
        r"delete\s+(?:the\s+)?line\s+([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"delete\s+(?:the\s+)?line\s+(\w+)",
    ]

    SUMMARIZE_PATTERNS = [
        r"^summarize(?:\s+(?:this\s+)?(?:file|code))?$",
        r"^summary\s+of\s+(?:this\s+)?(?:file|code)$",
        # Hindi: "कोड का सारांश दो" / "सारांश बताओ"
        r"^(?:कोड\s+(?:का\s+)?)?सारांश\s*(?:दो|बताओ|दीजिए)?$",
    ]
    NARRATE_FILE_PATTERNS = [
        r"^narrate(?:\s+(?:the\s+)?(?:file|code|whole\s+file))?$",
        r"^read\s+(?:the\s+)?(?:whole|entire|full)\s+(?:file|code)$",
        r"^read\s+(?:me\s+)?(?:the\s+)?(?:file|code)\s+(?:from\s+)?(?:start\s+to\s+(?:end|finish))?$",
        r"^(?:walk|talk)\s+(?:me\s+)?through\s+(?:the\s+)?(?:file|code)$",
        r"^(?:पूरा|पूरी)\s+(?:file|कोड|code)\s+(?:पढ़ो|सुनाओ|narrate\s*करो)$",
        r"^(?:कोड|file)\s+(?:को\s+)?(?:शुरू\s+से\s+अंत\s+तक\s+)?(?:पढ़ो|सुनाओ)$",
    ]

    DEMO_LIST_PATTERNS = [
        r"^(?:show|list)\s+(?:demos|examples|presets)$",
        r"^what\s+demos?\s+(?:are\s+)?(?:available|there)$",
        r"^demos?$",
        r"^(?:कौन\s+से\s+|क्या\s+)?(?:demos?|examples?)\s*(?:हैं|दिखाओ)?$",
    ]

    DEMO_RUN_PATTERNS = [
        r"^(?:run|load|play|start)\s+demo\s+(.+)$",
        r"^demo\s+(.+?)\s+(?:run|load|चलाओ)$",
        r"^(?:run|load|play|start)\s+(?:the\s+)?(\w+)\s+demo$",
        r"^demo\s+(\w+)$",
    ]

    PAUSE_VOICE_PATTERNS = [
        r"^pause$",
        r"^pause\s+voice(?:\s+(?:recognition|control|input))?$",
        r"^pause\s+please$",
        r"^(?:stop|halt)\s+listening$",
        r"^(?:mute|silence)\s+(?:the\s+)?(?:mic|microphone)?$",
        r"^voice\s+pause$",
        r"^go\s+(?:to\s+)?silent$",
        r"^(?:रुको\s+थोड़ा|pause\s*करो)$",
        r"^(?:आवाज़|voice)\s+(?:को\s+)?(?:रोको|बंद\s+करो|pause\s*करो)$",
        r"^सुनना\s+बंद\s+करो$",
    ]

    RESUME_VOICE_PATTERNS = [
        r"^resume$",
        r"^resume\s+voice(?:\s+(?:recognition|control|input))?$",
        r"^resume\s+please$",
        r"^(?:start|continue)\s+listening$",
        r"^(?:unmute|wake\s+up)$",
        r"^voice\s+resume$",
        r"^(?:are\s+you\s+)?(?:listening)\??$",
        r"^come\s+back$",
        r"^(?:आवाज़|voice)\s+(?:को\s+)?(?:चालू\s+करो|शुरू\s+करो|resume\s*करो)$",
        r"^(?:फिर\s+से\s+)?सुनो$",
    ]

    # Require an explicit code-generation verb at the start of the utterance and
    # at least 3 words in the prompt so ambient speech ("code for that exam")
    # cannot be misrouted to the LLM.
    GENERATE_CODE_PATTERNS = [
        r"^(?:please\s+)?(?:generate|write|create|make|build)\s+(?:a\s+|some\s+)?(?:python\s+)?code\s+(?:that|which|to|for)\s+(\S+(?:\s+\S+){2,})",
        r"^(?:please\s+)?(?:generate|write|create|make|build)\s+(?:a\s+|some\s+)?(?:python\s+)?(?:program|script|function)\s+(?:that|which|to|for)\s+(\S+(?:\s+\S+){2,})",
        r"^(?:please\s+)?(?:generate|write|create|make|build)\s+(?:a\s+|some\s+)?(?:python\s+)?code\s+for\s+(\S+(?:\s+\S+){2,})",
        r"^i\s+want\s+(?:python\s+)?code\s+(?:for|to|that)\s+(\S+(?:\s+\S+){2,})",
        # bare command — no prompt, will ask user
        r"^(?:generate|write|create|make)\s+(?:python\s+)?code$",
        # Hindi: "X के लिए कोड बनाओ" — require at least 2 words before the trigger
        r"^(\S+(?:\s+\S+){1,})\s+(?:के\s+लिए|का|की)\s+(?:कोड|code)\s+(?:बनाओ|लिखो|बनाइए|बनाइये)$",
        # Hindi: "code बनाओ X Y Z"
        r"^(?:कोड|code)\s+(?:बनाओ|लिखो)\s+(\S+(?:\s+\S+){2,})$",
    ]

    RENAME_SNIPPET_PATTERNS = [
        r"rename\s+snippet\s+([a-z0-9\-]+)\s+to\s+(.+)",
    ]

    SAVE_SNIPPET_NAMED_PATTERNS = [
        r"save\s+(?:snippet|code)\s+(?:as\s+|named?\s+)(.+)",
        r"save\s+(?:this\s+)?(?:as\s+|named?\s+)(.+)",
        # Hindi: "snippet नाम से सेव करो X"
        r"(?:snippet|कोड)\s+(?:को\s+)?(.+?)\s+(?:नाम\s+से\s+)?(?:सेव|save)\s*(?:करो|कीजिए)?",
    ]

    PREVIEW_SNIPPET_PATTERNS = [
        r"^preview\s+snippet\s+(\w+)$",
        r"^(?:peek|read)\s+(?:at\s+)?snippet\s+(\w+)$",
        r"^snippet\s+preview\s+(\w+)$",
        r"^snippet\s+(\w+)\s+(?:झलक|preview)$",
    ]

    # -----------------------------------------------------------------------
    # Voice code editing patterns
    # -----------------------------------------------------------------------

    INSERT_FUNCTION_PATTERNS = [
        r"insert\s+(?:a\s+)?function\s+(?:called\s+|named\s+)?(\w+)",
        r"add\s+(?:a\s+)?function\s+(?:called\s+|named\s+)?(\w+)",
        r"create\s+(?:a\s+)?function\s+(?:called\s+|named\s+)?(\w+)",
        # Hindi: "function जोड़ो जिसका नाम greet है"
        r"function\s+(\w+)\s+(?:जोड़ो|बनाओ|डालो)",
        r"(?:एक\s+)?function\s+(?:जोड़ो|बनाओ|डालो)\s+(?:नाम\s+)?(\w+)",
    ]

    INSERT_CLASS_PATTERNS = [
        r"insert\s+(?:a\s+)?class\s+(?:called\s+|named\s+)?(\w+)",
        r"add\s+(?:a\s+)?class\s+(?:called\s+|named\s+)?(\w+)",
        r"create\s+(?:a\s+)?class\s+(?:called\s+|named\s+)?(\w+)",
    ]

    INSERT_LINE_PATTERNS = [
        r"insert\s+(?:line\s+)?[\"']?(.+?)[\"']?\s+(?:at|on)\s+line\s+([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"add\s+(?:line\s+)?[\"']?(.+?)[\"']?\s+(?:at|on)\s+line\s+([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"insert\s+[\"'](.+?)[\"']\s+after\s+line\s+([\w\s]+?)(?:\s*$)",
    ]

    REPLACE_LINE_PATTERNS = [
        r"replace\s+line\s+([\w\s]+?)\s+with\s+[\"']?(.+?)[\"']?$",
        r"change\s+line\s+([\w\s]+?)\s+to\s+[\"']?(.+?)[\"']?$",
        r"set\s+line\s+([\w\s]+?)\s+to\s+[\"']?(.+?)[\"']?$",
    ]

    ADD_PARAMETER_PATTERNS = [
        r"add\s+(?:a\s+)?parameter\s+(?:called\s+|named\s+)?(\w+)(?:\s+to\s+(?:function\s+)?(\w+))?",
        r"add\s+(?:a\s+)?param\s+(?:called\s+|named\s+)?(\w+)(?:\s+to\s+(?:function\s+)?(\w+))?",
    ]

    INSERT_LOOP_PATTERNS = [
        r"insert\s+(?:a\s+)?(?:for\s+)?loop\s+(?:over\s+|for\s+)?(\w+)(?:\s+in\s+(\w+))?",
        r"add\s+(?:a\s+)?(?:for\s+)?loop\s+(?:over\s+|for\s+)?(\w+)(?:\s+in\s+(\w+))?",
        r"insert\s+(?:a\s+)?for\s+loop",
        r"add\s+(?:a\s+)?for\s+loop",
    ]

    INSERT_IF_PATTERNS = [
        r"insert\s+(?:an?\s+)?if\s+(?:statement\s+)?(?:for\s+|checking\s+)?(.+)",
        r"add\s+(?:an?\s+)?if\s+(?:statement\s+)?(?:for\s+|checking\s+)?(.+)",
    ]

    APPEND_LINE_PATTERNS = [
        r"append\s+[\"']?(.+?)[\"']?$",
        r"add\s+(?:a\s+)?(?:new\s+)?line\s+[\"']?(.+?)[\"']?$",
        r"write\s+[\"']?(.+?)[\"']?$",
        r"type\s+[\"']?(.+?)[\"']?$",
    ]

    # -----------------------------------------------------------------------
    # Semantic autocomplete patterns
    # -----------------------------------------------------------------------

    SUGGEST_NEXT_PATTERNS = [
        r"^suggest\s+(?:next\s+)?line$",
        r"^what\s+(?:comes|goes)\s+next$",
        r"^next\s+suggestion$",
        r"^complete\s+(?:this\s+)?line$",
        r"^what\s+should\s+i\s+(?:write|type)\s+next$",
        # Hindi: "अगली लाइन सुझाओ" / "क्या लिखूं"
        r"^अगली\s+(?:लाइन|line)\s+(?:सुझाओ|बताओ|suggest\s*करो)$",
        r"^(?:आगे\s+)?क्या\s+लिखूं$",
    ]

    CHOOSE_SUGGESTION_PATTERNS = [
        r"^choose\s+(?:option\s+)?(\w+)$",
        r"^(?:select|pick|use)\s+(?:option\s+)?(\w+)$",
        r"^(?:option\s+)?(\w+)$",
    ]

    NEXT_STEP_PATTERNS = [
        r"^(?:next|forward)\s+step$",
        r"^step\s+(?:forward|next)$",
        # Hindi: "अगला कदम" / "आगे बढ़ो"
        r"^अगला\s+(?:कदम|step)$",
        r"^आगे\s+(?:बढ़ो|जाओ)$",
    ]

    PREVIOUS_STEP_PATTERNS = [
        r"^(?:previous|back|prev)\s+step$",
        r"^step\s+(?:back|backward|previous)$",
        # Hindi: "पिछला कदम" / "पीछे जाओ"
        r"^पिछला\s+(?:कदम|step)$",
        r"^पीछे\s+(?:जाओ|बढ़ो)$",
    ]

    WHAT_CHANGED_PATTERNS = [
        r"^what\s+changed(?:\s+here)?$",
        r"^(?:state\s+change|show\s+change)$",
    ]

    READ_OUTPUT_PATTERNS = [
        r"^(?:speak|read|say)\s+(?:the\s+)?output$",
    ]

    REPEAT_PATTERNS = [
        r"^repeat(?:\s+that)?$",
        r"^again$",
        r"^say\s+that\s+again$",
        r"^repeat\s+last$",
    ]

    HELP_PATTERNS = [
        r"^help$",
        r"^show\s+help$",
        r"^what\s+can\s+(?:i\s+)?(?:do|say)$",
        r"^(?:i'?m\s+)?(?:lost|stuck|confused)$",
        r"^how\s+(?:do\s+i|does\s+this)\s+work$",
        r"^what\s+now$",
        r"^(?:i\s+)?(?:don'?t|do\s+not)\s+know\s+what\s+to\s+(?:do|say)$",
        r"^(?:tell|show)\s+me\s+(?:the\s+)?commands$",
        # Hindi
        r"^(?:मदद|सहायता|help)\s*(?:चाहिए|करो|दो|कीजिए)?$",
        r"^क्या\s+कर\s+सकते\s+हो$",
        r"^मैं\s+(?:क्या|कैसे)\s+करूं$",
        r"^समझ\s+नहीं\s+आ\s+रहा$",
        r"^madad$",
        r"^madat$",
        r"^madad\s+karo$",
        r"^help\s+me$",
    ]

    MORE_HELP_PATTERNS = [
        r"^more\s+help$",
        r"^full\s+help$",
        r"^all\s+commands$",
        r"^list\s+commands$",
        r"^पूरी\s+(?:मदद|help)$",
        r"^सभी\s+(?:कमांड|commands)$",
        r"^कमांड\s+(?:की\s+)?सूची$",
    ]

    # -----------------------------------------------------------------------
    # Execution story mode
    # -----------------------------------------------------------------------

    STORY_MODE_PATTERNS = [
        r"^(?:tell|narrate|explain|describe)\s+(?:the\s+)?(?:execution\s+)?story$",
        r"^(?:story|narrate)\s+(?:this\s+)?(?:execution|run|code)$",
        r"^what\s+(?:happened|did\s+the\s+code\s+do)\s+(?:when\s+it\s+ran)?$",
        r"^execution\s+story$",
        r"^(?:कहानी|narrate\s+करो|explain\s+करो)\s*(?:execution)?$",
    ]

    # -----------------------------------------------------------------------
    # Audio breakpoint debugger
    # -----------------------------------------------------------------------

    SET_BREAKPOINT_PATTERNS = [
        r"set\s+(?:a\s+)?breakpoint\s+(?:at\s+)?(?:line\s+)?([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"(?:pause|stop)\s+(?:at\s+)?(?:line\s+)?([\w\s]+?)(?:\s*$|\s+(?:please|now))",
        r"break\s+(?:at\s+)?(?:line\s+)?([\w\s]+?)(?:\s*$|\s+(?:please|now))",
    ]

    CLEAR_BREAKPOINT_PATTERNS = [
        r"^(?:clear|remove|delete)\s+(?:all\s+)?breakpoints?$",
        r"^(?:breakpoints?\s+)?(?:clear|remove|delete)\s+(?:all\s+)?breakpoints?$",
    ]

    WATCH_VARIABLE_PATTERNS = [
        r"watch\s+(?:variable\s+)?(\w+)",
        r"monitor\s+(?:variable\s+)?(\w+)",
        r"keep\s+(?:an\s+)?eye\s+on\s+(?:variable\s+)?(\w+)",
    ]

    DEBUG_CONTINUE_PATTERNS = [
        r"^continue(?:\s+(?:debugging|execution))?$",
        r"^(?:resume|proceed)(?:\s+(?:debugging|execution))?$",
        r"^जारी\s+रखो$",
    ]

    DEBUG_STEP_IN_PATTERNS = [
        r"^step\s+in(?:to)?$",
        r"^(?:go\s+)?inside\s+(?:the\s+)?function$",
    ]

    DEBUG_STEP_OUT_PATTERNS = [
        r"^step\s+out(?:\s+of)?(?:\s+(?:the\s+)?function)?$",
        r"^(?:exit|leave)\s+(?:the\s+)?function$",
    ]

    # -----------------------------------------------------------------------
    # Learning / mentor mode
    # -----------------------------------------------------------------------

    MENTOR_MODE_PATTERNS = [
        r"^(?:start\s+)?(?:learning|mentor|tutor)\s+mode$",
        r"^(?:teach|tutor)\s+me$",
        r"^(?:मुझे\s+सिखाओ|learning\s+mode\s+शुरू\s+करो)$",
    ]

    QUIZ_ME_PATTERNS = [
        r"^quiz\s+me(?:\s+on\s+(.+))?$",
        r"^(?:test|challenge)\s+me(?:\s+on\s+(.+))?$",
        r"^give\s+me\s+(?:a\s+)?(?:quiz|challenge|test)(?:\s+on\s+(.+))?$",
        r"^(?:मुझे\s+quiz\s+करो|test\s+करो)(?:\s+(.+))?$",
    ]

    EXPLAIN_CONCEPT_PATTERNS = [
        r"explain\s+(.+?)\s+(?:like\s+i['\u2019]?m\s+new|for\s+(?:a\s+)?beginner|simply|in\s+simple\s+(?:terms|words))",
        r"what\s+(?:is|are)\s+(.+?)\s+in\s+simple\s+(?:terms|words)",
        r"(?:मुझे\s+)?(.+?)\s+(?:समझाओ|explain\s+करो)\s*(?:simply|simply\s+में)?",
    ]

    BUG_CHALLENGE_PATTERNS = [
        r"explain\s+(.+?)(?:\s+to\s+me)?\s+(?:like\s+i['\u2019]?m\s+new|for\s+(?:a\s+)?beginner|simply|in\s+simple\s+(?:terms|words))"
        r"^(?:give\s+me\s+)?(?:a\s+)?bug\s+(?:fixing\s+)?challenge$",
        r"^(?:debug\s+)?challenge(?:\s+me)?$",
        r"^(?:एक\s+)?bug\s+(?:challenge|ढूंढो)$",
    ]

    # ----- Pre-flight input controls -----
    SET_INPUTS_PATTERNS = [
        r"^set\s+inputs?\s+to\s+(.+)$",
        r"^use\s+inputs?\s+(.+)$",
        r"^inputs?\s+are\s+(.+)$",
        r"^(?:पहले\s+से\s+|preflight\s+)?inputs?\s+(.+?)\s+(?:set|डालो|दो)$",
    ]
    CLEAR_INPUTS_PATTERNS = [
        r"^clear\s+inputs?$",
        r"^remove\s+(?:all\s+)?inputs?$",
        r"^reset\s+inputs?$",
        r"^inputs?\s+(?:साफ|खाली)\s*करो$",
    ]
    LIST_INPUTS_PATTERNS = [
        r"^(?:list|show|read)\s+(?:my\s+)?inputs?$",
        r"^what\s+(?:are\s+my\s+)?inputs?$",
        r"^inputs?\s+(?:सुनाओ|बताओ)$",
    ]
    LIVE_INPUT_MODE_PATTERNS = [
        r"^(?:switch\s+to\s+)?live\s+input(?:\s+mode)?$",
        r"^interactive\s+(?:mode|input)$",
        r"^live\s+(?:run|mode)$",
        r"^(?:लाइव|interactive)\s+(?:मोड|mode)$",
    ]
    PREFLIGHT_INPUT_MODE_PATTERNS = [
        r"^(?:switch\s+to\s+)?(?:pre-?flight|preflight)\s+(?:input\s+)?mode$",
        r"^(?:pre-?flight|preflight)\s+inputs?$",
        r"^batch\s+(?:input\s+)?mode$",
    ]

    # ----- Voice macros -----
    SAVE_MACRO_PATTERNS = [
        r"^remember\s+(?:this\s+)?as\s+(.+)$",
        r"^save\s+(?:this\s+)?(?:as\s+)?macro\s+(.+)$",
        r"^macro\s+save\s+(.+)$",
        r"^(?:इसे\s+)?(.+?)\s+(?:नाम\s+से\s+)?(?:याद|macro)\s*(?:रखो|करो)$",
    ]
    USE_MACRO_PATTERNS = [
        r"^use\s+macro\s+(.+)$",
        r"^(?:run|load)\s+macro\s+(.+)$",
        r"^macro\s+(.+?)\s+(?:use|run|load)$",
        r"^macro\s+(.+)$",  # last because greediest
        r"^(.+?)\s+macro\s+(?:चलाओ|use\s*करो)$",
    ]
    LIST_MACROS_PATTERNS = [
        r"^list\s+macros?$",
        r"^show\s+(?:my\s+)?macros?$",
        r"^what\s+macros?\s+(?:do\s+i\s+have|are\s+saved)$",
        r"^macros?\s+(?:की\s+सूची|बताओ)$",
    ]

    # ----- Output bookmarks -----
    BOOKMARK_OUTPUT_PATTERNS = [
        r"^bookmark\s+(?:this|here)?(?:\s+as\s+(.+))?$",
        r"^mark\s+(?:this|here)?(?:\s+as\s+(.+))?$",
        r"^(?:यहां|यह)\s+bookmark\s*(?:करो)?(?:\s+(?:नाम\s+)?(.+))?$",
    ]
    READ_BOOKMARK_PATTERNS = [
        r"^read\s+from\s+bookmark(?:\s+(.+))?$",
        r"^(?:go\s+to|jump\s+to)\s+bookmark(?:\s+(.+))?$",
        r"^bookmark(?:\s+(.+))?\s+(?:से|से\s+पढ़ो|पढ़ो)$",
    ]
    LIST_BOOKMARKS_PATTERNS = [
        r"^list\s+bookmarks?$",
        r"^show\s+(?:my\s+)?bookmarks?$",
        r"^bookmarks?$",
        r"^bookmarks?\s+(?:बताओ|सूची)$",
    ]

    # ----- Where am I (live execution position) -----
    WHERE_AM_I_PATTERNS = [
        r"^where\s+am\s+i(?:\s+in\s+execution)?$",
        r"^(?:current\s+)?(?:execution\s+)?position$",
        r"^what\s+line\s+(?:is\s+running|am\s+i\s+on)$",
        r"^(?:मैं\s+)?कहां\s+हूं$",
        r"^कौन\s+सी\s+line$",
    ]

    # ----- Beginner explanation -----
    EXPLAIN_SIMPLY_PATTERNS = [
        r"^explain\s+(?:like\s+i'?m\s+(?:five|new|a\s+beginner)|simpler|simply|in\s+plain\s+(?:words|english))$",
        r"^(?:simpler|too\s+complicated|i\s+don'?t\s+understand)$",
        r"^(?:और\s+आसान|simple\s+में|बच्चे\s+की\s+तरह)\s*(?:समझाओ)?$",
    ]

    # ----- Diff narration -----
    NARRATE_DIFF_PATTERNS = [
        r"^(?:what'?s|whats)\s+different$",
        r"^(?:narrate|tell\s+me)\s+(?:the\s+)?diff(?:erence)?$",
        r"^(?:what\s+)?changed\s+(?:in|from)\s+(?:the\s+)?(?:last\s+)?(?:run|output)$",
        r"^output\s+diff$",
        r"^(?:पिछले\s+से\s+)?क्या\s+अलग\s+है$",
    ]

    START_TUTORIAL_PATTERNS = [
        r"^(?:start|open|begin|launch)\s+tutorial$",
        r"^tutorial$",
        r"^tutorial\s+(?:शुरू\s+करो|खोलो)$",
    ]

    SKIP_TUTORIAL_PATTERNS = [
        r"^skip\s+tutorial$",
        r"^(?:close|exit|stop)\s+tutorial$",
        r"^tutorial\s+(?:बंद\s+करो|छोड़ो)$",
    ]

    TUTORIAL_NEXT_PATTERNS = [
        r"^tutorial\s+next$",
        r"^(?:आगे\s+बढ़ो|next\s+करो)$",
    ]

    # -----------------------------------------------------------------------
    # Intent map — order defines precedence (most specific first)
    # -----------------------------------------------------------------------

    def __init__(self) -> None:
        self.intent_map = self._build_intent_map()

    def _build_intent_map(self) -> Dict[str, List[str]]:
        """Return ordered intent → patterns mapping. More specific intents first."""
        return {
            # Line-level operations (specific verbs before generic navigation)
            "read_line":      self.READ_LINE_PATTERNS,
            "describe_line":  self.DESCRIBE_LINE_PATTERNS,
            "delete_line":    self.DELETE_LINE_PATTERNS,
            # General line navigation — tighter patterns, no bare \bline\b catch-all
            "goto_line":      self.GOTO_LINE_PATTERNS,
            # Function / class navigation
            "read_function":  self.READ_FUNCTION_PATTERNS,
            "find_function":  self.FIND_FUNCTION_PATTERNS,
            "sonify_function": self.SONIFY_FUNCTION_PATTERNS,
            "find_class":     self.FIND_CLASS_PATTERNS,
            "sonify_class":   self.SONIFY_CLASS_PATTERNS,
            # Execution and analysis
            "run":            self.RUN_PATTERNS,
            "analyze_deep":   self.ANALYZE_DEEP_PATTERNS,
            "analyze":        self.ANALYZE_PATTERNS,
            "fix":            self.FIX_PATTERNS,
            "advise":         self.ADVISE_PATTERNS,
            "summarize":      self.SUMMARIZE_PATTERNS,
            "narrate_file":   self.NARRATE_FILE_PATTERNS,
            "demo_run":       self.DEMO_RUN_PATTERNS,
            "demo_list":      self.DEMO_LIST_PATTERNS,
            # Pause/resume must come BEFORE generate_code because "pause" is short
            # enough that fuzzy matching could route it to other intents otherwise.
            "pause_voice":    self.PAUSE_VOICE_PATTERNS,
            "resume_voice":   self.RESUME_VOICE_PATTERNS,
            "generate_code":  self.GENERATE_CODE_PATTERNS,
            "rename_snippet":      self.RENAME_SNIPPET_PATTERNS,
            "save_snippet_named":  self.SAVE_SNIPPET_NAMED_PATTERNS,
            "preview_snippet":     self.PREVIEW_SNIPPET_PATTERNS,
            # Voice code editing
            "insert_function":     self.INSERT_FUNCTION_PATTERNS,
            "insert_class":        self.INSERT_CLASS_PATTERNS,
            "insert_line":         self.INSERT_LINE_PATTERNS,
            "replace_line":        self.REPLACE_LINE_PATTERNS,
            "add_parameter":       self.ADD_PARAMETER_PATTERNS,
            "insert_loop":         self.INSERT_LOOP_PATTERNS,
            "insert_if":           self.INSERT_IF_PATTERNS,
            "append_line":         self.APPEND_LINE_PATTERNS,
            # repeat MUST come before choose_suggestion — ^(\w+)$ matches "repeat" too
            "repeat":              self.REPEAT_PATTERNS,
            "help":                self.HELP_PATTERNS,
            "more_help":           self.MORE_HELP_PATTERNS,
            # Semantic autocomplete
            "suggest_next":        self.SUGGEST_NEXT_PATTERNS,
            "choose_suggestion":   self.CHOOSE_SUGGESTION_PATTERNS,
            "clear_editor":   self.CLEAR_EDITOR_PATTERNS,
            "set_color_mode": self.SET_COLOR_MODE_PATTERNS,
            "read_output":    self.READ_OUTPUT_PATTERNS,
            # Structure and playback
            "show_structure": self.SHOW_STRUCTURE_PATTERNS,
            "sonify_block":   self.SONIFY_BLOCK_PATTERNS,
            "locate_error":   self.ERROR_PATTERNS,
            "next_step":      self.NEXT_STEP_PATTERNS,
            "previous_step":  self.PREVIOUS_STEP_PATTERNS,
            "what_changed":   self.WHAT_CHANGED_PATTERNS,
            # Story mode
            "story_mode":          self.STORY_MODE_PATTERNS,
            # Breakpoint debugger
            "set_breakpoint":      self.SET_BREAKPOINT_PATTERNS,
            "clear_breakpoints":   self.CLEAR_BREAKPOINT_PATTERNS,
            "watch_variable":      self.WATCH_VARIABLE_PATTERNS,
            "debug_continue":      self.DEBUG_CONTINUE_PATTERNS,
            "debug_step_in":       self.DEBUG_STEP_IN_PATTERNS,
            "debug_step_out":      self.DEBUG_STEP_OUT_PATTERNS,
            # Mentor mode
            "mentor_mode":         self.MENTOR_MODE_PATTERNS,
            "quiz_me":             self.QUIZ_ME_PATTERNS,
            "explain_concept":     self.EXPLAIN_CONCEPT_PATTERNS,
            "bug_challenge":       self.BUG_CHALLENGE_PATTERNS,
            "start_tutorial":      self.START_TUTORIAL_PATTERNS,
            "skip_tutorial":       self.SKIP_TUTORIAL_PATTERNS,
            "tutorial_next":       self.TUTORIAL_NEXT_PATTERNS,
            # Input mechanisms
            "set_inputs":          self.SET_INPUTS_PATTERNS,
            "clear_inputs":        self.CLEAR_INPUTS_PATTERNS,
            "list_inputs":         self.LIST_INPUTS_PATTERNS,
            "live_input_mode":     self.LIVE_INPUT_MODE_PATTERNS,
            "preflight_input_mode": self.PREFLIGHT_INPUT_MODE_PATTERNS,
            # Voice macros
            "save_macro":          self.SAVE_MACRO_PATTERNS,
            "use_macro":           self.USE_MACRO_PATTERNS,
            "list_macros":         self.LIST_MACROS_PATTERNS,
            # Output bookmarks
            "bookmark_output":     self.BOOKMARK_OUTPUT_PATTERNS,
            "read_bookmark":       self.READ_BOOKMARK_PATTERNS,
            "list_bookmarks":      self.LIST_BOOKMARKS_PATTERNS,
            # Live execution position
            "where_am_i":          self.WHERE_AM_I_PATTERNS,
            # Beginner explanation + diff narration
            "explain_simply":      self.EXPLAIN_SIMPLY_PATTERNS,
            "narrate_diff":        self.NARRATE_DIFF_PATTERNS,
        }

    # -----------------------------------------------------------------------
    # Number parsing
    # -----------------------------------------------------------------------

    def _word_to_number(self, word: str) -> Optional[int]:
        """Convert a spoken or written number into an integer.
        Supports: digit strings, single words, two-word compounds (twenty five),
        and three/four-word hundreds compounds (one hundred fifty, two hundred forty two)."""
        word = word.lower().strip()

        # Digit string
        try:
            return int(word)
        except ValueError:
            pass

        # Single word: "five", "twenty", "nineteen", or any Hindi number
        if word in WORD_TO_NUMBER:
            return WORD_TO_NUMBER[word]

        parts = word.split()

        # Two-word compound: "twenty five", "forty two"
        if len(parts) == 2:
            tens_val = _TENS.get(parts[0])
            ones_val = _ONES.get(parts[1])
            if tens_val is not None and ones_val is not None and ones_val < 10:
                return tens_val + ones_val

        # Three-word compound: "one hundred fifty" / "two hundred ten"
        if len(parts) == 3 and parts[1] == "hundred":
            hundreds = _ONES.get(parts[0])
            rest = WORD_TO_NUMBER.get(parts[2])
            if hundreds is not None and 1 <= hundreds <= 9 and rest is not None and rest < 100:
                return hundreds * 100 + rest

        # Four-word compound: "two hundred forty two"
        if len(parts) == 4 and parts[1] == "hundred":
            hundreds = _ONES.get(parts[0])
            tens_val = _TENS.get(parts[2])
            ones_val = _ONES.get(parts[3])
            if hundreds is not None and 1 <= hundreds <= 9 and tens_val is not None and ones_val is not None and ones_val < 10:
                return hundreds * 100 + tens_val + ones_val

        # "X hundred" exactly
        if len(parts) == 2 and parts[1] == "hundred":
            hundreds = _ONES.get(parts[0])
            if hundreds is not None and 1 <= hundreds <= 9:
                return hundreds * 100

        return None

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def parse(self, text: str) -> Dict:
        text = text.strip().lower()

        if not text:
            return {"intent": None, "slots": {}, "confidence": 0.0, "original": text}

        for intent, patterns in self.intent_map.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if not match:
                    continue

                slots = self._extract_slots(intent, match, text)

                # Slot-presence guards: if a required slot couldn't be parsed,
                # skip this match and continue trying other patterns.
                if intent in ("goto_line", "read_line") and "line_number" not in slots:
                    continue
                if intent in ("read_function", "find_function", "sonify_function") \
                        and "function_name" not in slots:
                    continue
                if intent in ("find_class", "sonify_class") \
                        and "class_name" not in slots:
                    continue
                if intent == "describe_line" and "line_number" not in slots:
                    continue
                if intent == "delete_line" and "line_number" not in slots:
                    continue
                if intent == "generate_code":
                    if "prompt" in slots and not slots["prompt"]:
                        del slots["prompt"]
                if intent == "save_snippet_named" and "name" not in slots:
                    continue
                if intent == "replace_line" and ("line_number" not in slots or "text" not in slots):
                    continue
                if intent == "insert_line" and ("line_number" not in slots or "text" not in slots):
                    continue
                if intent == "append_line" and "text" not in slots:
                    continue
                if intent == "insert_function" and "function_name" not in slots:
                    continue
                if intent == "insert_class" and "class_name" not in slots:
                    continue
                if intent == "set_breakpoint" and "line_number" not in slots:
                    continue
                if intent == "explain_concept" and "concept" not in slots:
                    continue
                if intent == "set_inputs" and "values" not in slots:
                    continue
                if intent == "save_macro" and "name" not in slots:
                    continue
                if intent == "use_macro" and "name" not in slots:
                    continue
                if intent == "set_color_mode" and "mode" not in slots:
                    continue
                
                return {
                    "intent": intent,
                    "slots": slots,
                    "confidence": 0.95,
                    "original": text,
                }

        return {
            "intent": None,
            "slots": {},
            "confidence": 0.0,
            "original": text,
        }

    def _extract_slots(self, intent: str, match: re.Match, text: str) -> Dict:
        """Extract and validate slots from a regex match."""
        slots: Dict = {}

        if intent in ("goto_line", "read_line", "describe_line", "delete_line"):
            if match.groups():
                raw = match.group(1).strip()
                num = self._word_to_number(raw)
                if num is not None:
                    slots["line_number"] = num

        elif intent in ("read_function", "find_function", "sonify_function"):
            if match.groups():
                slots["function_name"] = match.group(1).strip()

        elif intent in ("find_class", "sonify_class"):
            if match.groups():
                slots["class_name"] = match.group(1).strip()

        elif intent == "generate_code":
            if match.groups() and match.group(1):
                prompt = match.group(1).strip()
                if prompt:
                    slots["prompt"] = prompt


        elif intent == "rename_snippet":
            if match.groups() and len(match.groups()) >= 2:
                slots["id"] = match.group(1).strip()
                slots["new_name"] = match.group(2).strip()

        elif intent == "save_snippet_named":
            if match.groups() and match.group(1):
                slots["name"] = match.group(1).strip()

        elif intent == "insert_function":
            if match.groups() and match.group(1):
                slots["function_name"] = match.group(1).strip()

        elif intent == "insert_class":
            if match.groups() and match.group(1):
                slots["class_name"] = match.group(1).strip()

        elif intent == "insert_loop":
            if match.groups():
                slots["loop_var"]    = match.group(1).strip() if match.group(1) else "i"
                slots["iterable"]    = match.group(2).strip() if len(match.groups()) >= 2 and match.group(2) else "range(10)"

        elif intent == "insert_if":
            if match.groups() and match.group(1):
                slots["condition"] = match.group(1).strip()

        elif intent == "append_line":
            if match.groups() and match.group(1):
                slots["text"] = match.group(1).strip()

        elif intent == "replace_line":
            if match.groups() and len(match.groups()) >= 2:
                raw = match.group(1).strip()
                num = self._word_to_number(raw)
                if num is not None:
                    slots["line_number"] = num
                if match.group(2):
                    slots["text"] = match.group(2).strip()

        elif intent == "insert_line":
            if match.groups() and len(match.groups()) >= 2:
                slots["text"] = match.group(1).strip()
                raw = match.group(2).strip()
                num = self._word_to_number(raw)
                if num is not None:
                    slots["line_number"] = num

        elif intent == "add_parameter":
            if match.groups() and match.group(1):
                slots["param_name"]    = match.group(1).strip()
                slots["function_name"] = match.group(2).strip() if len(match.groups()) >= 2 and match.group(2) else None

        elif intent == "choose_suggestion":
            if match.groups() and match.group(1):
                raw = match.group(1).strip()
                num = self._word_to_number(raw)
                slots["choice"] = num if num is not None else raw

        elif intent == "set_breakpoint":
            if match.groups() and match.group(1):
                raw = match.group(1).strip()
                num = self._word_to_number(raw)
                if num is not None:
                    slots["line_number"] = num

        elif intent == "watch_variable":
            if match.groups() and match.group(1):
                slots["variable"] = match.group(1).strip()

        elif intent == "quiz_me":
            if match.groups() and match.group(1):
                slots["topic"] = match.group(1).strip()

        elif intent == "explain_concept":
            if match.groups() and match.group(1):
                slots["concept"] = match.group(1).strip()

        elif intent == "demo_run":
            if match.groups() and match.group(1):
                slots["preset"] = match.group(1).strip().lower()

        elif intent == "preview_snippet":
            if match.groups() and match.group(1):
                slots["snippet_id"] = match.group(1).strip()

        elif intent == "set_color_mode":
            if match.groups() and match.group(1):
                raw = match.group(1).strip().lower().replace(' ', '')
                # Map natural phrases to the actual mode names
                aliases = {
                    'redblind': 'protanopia',
                    'greenblind': 'deuteranopia',
                    'blueblind': 'tritanopia',
                    'highcontrast': 'high-contrast',
                    'normal': 'default',
                    'standard': 'default',
                }
                slots["mode"] = aliases.get(raw, raw)
            elif "off" in text or "disable" in text or "reset" in text:
                slots["mode"] = "default"

        elif intent == "set_inputs":
            if match.groups() and match.group(1):
                raw = match.group(1).strip()
                # Split on " and ", commas, semicolons. Keeps "Alice" and "17"
                # together in 'Alice and 17'. Cap at 50 items, 1000 chars each.
                parts = re.split(r'\s*(?:,|;|\band\b)\s*', raw, flags=re.IGNORECASE)
                values = [p.strip() for p in parts if p.strip()]
                if values:
                    slots["values"] = values[:50]

        elif intent == "save_macro":
            if match.groups() and match.group(1):
                # Sanitize: lowercase, strip, allow safe chars including
                # Devanagari (U+0900–U+097F) so Hindi macro names work.
                name = match.group(1).strip().lower()
                name = re.sub(r'[^a-z0-9 _\u0900-\u097f-]', '', name)[:64].strip()
                if name:
                    slots["name"] = name

        elif intent == "use_macro":
            if match.groups() and match.group(1):
                name = match.group(1).strip().lower()
                name = re.sub(r'[^a-z0-9 _\u0900-\u097f-]', '', name)[:64].strip()
                if name:
                    slots["name"] = name

        elif intent == "bookmark_output":
            if match.groups() and len(match.groups()) >= 1 and match.group(1):
                label = match.group(1).strip().lower()[:64]
                if label:
                    slots["label"] = label

        elif intent == "read_bookmark":
            if match.groups() and len(match.groups()) >= 1 and match.group(1):
                slots["label"] = match.group(1).strip().lower()[:64]

        return slots

    def get_confidence(self, text: str) -> float:
        """Return confidence score (0.0–1.0) for the best-matching intent."""
        return self.parse(text).get("confidence", 0.0)

    def disambiguate(self, text: str, candidates: List[str]) -> Optional[str]:
       
        raise NotImplementedError(
            "disambiguate() is not yet implemented. "
            "Use parse() directly and inspect the confidence score."
        )


# ---------------------------------------------------------------------------
# Thread-safe lazy singleton
# ---------------------------------------------------------------------------

_parser: Optional[IntentParser] = None
_parser_lock = threading.Lock()


def get_parser() -> IntentParser:
    """Get or create the global IntentParser instance (thread-safe)."""
    global _parser
    if _parser is None:
        with _parser_lock:
            if _parser is None:
                _parser = IntentParser()
    return _parser


def parse_intent(text: str) -> Dict:
    """Convenience function: parse a voice command string into intent + slots."""
    return get_parser().parse(text)