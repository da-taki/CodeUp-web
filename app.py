from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

from flask import Flask, g, jsonify, render_template, request, send_from_directory

__version__ = "1.0.0-html"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")

SESSION_COOKIE_NAME = "codeup_html_session"
SESSION_COOKIE_MAX_AGE = 3600 * 24 * 7
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = None if os.environ.get("FLASK_TESTING", "false").lower() == "true" else "Lax"

DATA_DIR = os.environ.get("DATA_DIR", ".")
MAX_REQUEST_SIZE = 1_000_000
MAX_HTML_SIZE = 100_000
MAX_MESSAGE_SIZE = 20_000
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "30"))

_ai_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="codeup-ai")
_ai_lock = threading.Lock()
_ai_active = 0
_ALLOWED_ORIGINS = {
    origin.strip().lower()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}


def safejson() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _testing_mode() -> bool:
    return os.environ.get("FLASK_TESTING", "false").lower() == "true"


def _sanitize_id(value: str | None) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]", "", value or "")[:64]
    return clean or str(uuid.uuid4())


def get_session_id() -> str:
    cached = getattr(g, "session_id", None)
    if cached:
        return cached
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    session_id = _sanitize_id(cookie_value)
    g.session_id = session_id
    g.needs_session_cookie = not cookie_value
    return session_id


@app.after_request
def set_session_cookie(response):
    if getattr(g, "needs_session_cookie", False):
        response.set_cookie(
            SESSION_COOKIE_NAME,
            get_session_id(),
            max_age=SESSION_COOKIE_MAX_AGE,
            secure=SESSION_COOKIE_SECURE,
            httponly=SESSION_COOKIE_HTTPONLY,
            samesite=SESSION_COOKIE_SAMESITE,
        )
    return response


@app.before_request
def validate_request_size():
    if request.content_length and request.content_length > MAX_REQUEST_SIZE:
        return jsonify({"success": False, "error": "Request too large (max 1MB)"}), 413
    return None


@app.before_request
def enforce_same_origin():
    if request.method not in {"POST", "PUT", "DELETE", "PATCH"}:
        return None

    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    host = request.headers.get("Host", "").lower()

    if not origin and not referer:
        if _testing_mode():
            return None
        return jsonify({"success": False, "error": "Missing Origin/Referer header"}), 403

    if origin:
        origin_lower = origin.lower()
        origin_host = origin_lower.split("://", 1)[-1]
        if origin_host == host or origin_lower in _ALLOWED_ORIGINS:
            return None
        return jsonify({"success": False, "error": "Cross-origin request blocked"}), 403

    if referer:
        parsed = urlparse(referer)
        referer_host = parsed.netloc.lower()
        referer_origin = f"{parsed.scheme}://{parsed.netloc}".lower()
        if referer_host == host or referer_origin in _ALLOWED_ORIGINS:
            return None
        return jsonify({"success": False, "error": "Cross-origin request blocked"}), 403

    return None


def _data_path(*parts: str) -> str:
    path = os.path.join(DATA_DIR, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _html_memory_path(session_id: str | None = None) -> str:
    return _data_path("html_memory", f"{_sanitize_id(session_id or get_session_id())}.json")


def _student_site_dir(session_id: str | None = None) -> str:
    path = os.path.join(DATA_DIR, "student_sites", _sanitize_id(session_id or get_session_id()))
    os.makedirs(path, exist_ok=True)
    return path


def _load_html_memory(session_id: str | None = None) -> dict[str, Any]:
    path = _html_memory_path(session_id)
    if not os.path.exists(path):
        return {"history": [], "last_html": "", "last_url": ""}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return {
                "history": data.get("history", []) if isinstance(data.get("history"), list) else [],
                "last_html": str(data.get("last_html", "")),
                "last_url": str(data.get("last_url", "")),
            }
    except Exception:
        pass
    return {"history": [], "last_html": "", "last_url": ""}


def _save_html_memory(data: dict[str, Any], session_id: str | None = None) -> None:
    history = data.get("history", [])
    data["history"] = history[-30:] if isinstance(history, list) else []
    path = _html_memory_path(session_id)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def _append_memory(prompt: str = "", note: str = "", html: str = "", url: str = "") -> dict[str, Any]:
    memory = _load_html_memory()
    if prompt or note or url:
        memory.setdefault("history", []).append(
            {"prompt": prompt, "note": note, "url": url, "timestamp": time.time()}
        )
    if html:
        memory["last_html"] = html
    if url:
        memory["last_url"] = url
    _save_html_memory(memory)
    return memory


def _wrap_html(fragment: str) -> str:
    if "<html" in fragment.lower():
        return fragment
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>CodeUp Site</title></head>\n"
        f"<body>\n{fragment}\n</body>\n</html>"
    )


def _extract_html(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidate = match.group(1).strip() if match else text.strip()
    lowered = candidate.lower()
    start = lowered.find("<!doctype html")
    if start == -1:
        start = lowered.find("<html")
    if start > 0:
        candidate = candidate[start:].strip()
    return _wrap_html(candidate)


def _call_ollama(system_prompt: str, user_prompt: str, temperature: float) -> str | None:
    if os.environ.get("OLLAMA_ENABLED", "0") != "1":
        return None
    try:
        import requests

        response = requests.post(
            f"{os.environ.get('OLLAMA_URL', 'http://localhost:11434').rstrip('/')}/api/chat",
            json={
                "model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"temperature": temperature, "num_predict": 4096},
                "stream": False,
            },
            timeout=AI_TIMEOUT,
        )
        response.raise_for_status()
        content = (response.json().get("message") or {}).get("content", "").strip()
        return content or None
    except Exception:
        return None


def call_ai(system_prompt: str, user_prompt: str, temperature: float = 0.25, language: str = "en") -> str:
    if os.environ.get("GEMINI_ENABLED", "1") != "1":
        local = _call_ollama(system_prompt, user_prompt, temperature)
        return local or "AI service disabled"

    xai_key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    if not xai_key and not groq_key:
        local = _call_ollama(system_prompt, user_prompt, temperature)
        return local or "AI service not configured. Please set XAI_API_KEY, GROK_API_KEY, or GROQ_API_KEY."

    prompt = system_prompt
    if language == "hi":
        prompt = f"Reply in natural Hindi or Hinglish for a blind student. {system_prompt}"

    def run_call() -> str:
        global _ai_active
        with _ai_lock:
            _ai_active += 1
        try:
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_prompt},
            ]
            if xai_key:
                import requests

                response = requests.post(
                    os.environ.get("XAI_API_URL", "https://api.x.ai/v1/chat/completions"),
                    headers={"Authorization": f"Bearer {xai_key}", "Content-Type": "application/json"},
                    json={
                        "model": os.environ.get("XAI_MODEL", os.environ.get("GROK_MODEL", "grok-3-mini")),
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": 4096,
                    },
                    timeout=AI_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()

            from groq import Groq

            response = Groq(api_key=groq_key).chat.completions.create(
                model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=messages,
                temperature=temperature,
                max_tokens=4096,
            )
            return response.choices[0].message.content.strip()
        finally:
            with _ai_lock:
                _ai_active -= 1

    with _ai_lock:
        if _ai_active >= 3:
            local = _call_ollama(system_prompt, user_prompt, temperature)
            return local or "AI service is busy. Please try again in a moment."

    future = _ai_executor.submit(run_call)
    try:
        return future.result(timeout=AI_TIMEOUT + 1)
    except Exception as exc:
        local = _call_ollama(system_prompt, user_prompt, temperature)
        return local or f"AI service had a problem: {str(exc)[:120]}"


@app.route("/")
def landing():
    return render_template("index.html")


@app.route("/ide")
def ide():
    return render_template("index.html")


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok", "version": __version__})


@app.route("/api-config", methods=["POST"])
def api_config():
    body = safejson()
    key = str(body.get("apiKey") or body.get("xaiKey") or "").strip()
    if key:
        os.environ["XAI_API_KEY"] = key
    return jsonify({"success": True, "provider": "xAI/Grok" if key else "environment"})


@app.route("/publish-site", methods=["POST"])
def publish_site():
    body = safejson()
    html = str(body.get("html") or "")
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400

    html = _wrap_html(html)
    session_id = get_session_id()
    site_dir = _student_site_dir(session_id)
    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(html)

    url = f"/student-site/{session_id}/"
    _append_memory(note="Published website preview", html=html, url=url)
    return jsonify({"success": True, "url": url})


@app.route("/student-site/<session_id>/")
def student_site(session_id: str):
    return send_from_directory(_student_site_dir(_sanitize_id(session_id)), "index.html")


@app.route("/html-memory", methods=["GET", "POST"])
def html_memory():
    if request.method == "GET":
        return jsonify({"success": True, "memory": _load_html_memory()})

    body = safejson()
    html = str(body.get("html") or "")
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    memory = _append_memory(
        prompt=str(body.get("prompt") or "").strip(),
        note=str(body.get("note") or "").strip(),
        html=html,
        url=str(body.get("url") or "").strip(),
    )
    return jsonify({"success": True, "memory": memory})


@app.route("/html-chat", methods=["POST"])
def html_chat():
    body = safejson()
    message = str(body.get("message") or "").strip()
    html = str(body.get("html") or "")
    language = str(body.get("language") or "en")

    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty"}), 400
    if len(message) > MAX_MESSAGE_SIZE:
        return jsonify({"success": False, "error": f"Message too large (max {MAX_MESSAGE_SIZE} bytes)"}), 413
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413

    memory = _load_html_memory()
    current_html = html or memory.get("last_html", "")
    recent = "\n".join(
        f"- {item.get('prompt') or item.get('note')}"
        for item in memory.get("history", [])[-8:]
        if isinstance(item, dict)
    )
    system = (
        "You are CodeUp HTML, a conversational website-building guide for blind and visually impaired students. "
        "Explain what students can do, describe the current page, suggest improvements, and keep responses short enough for speech. "
        "Do not return code from chat; for building, tell the student to say or type 'Build a website for ...'."
    )
    user = (
        f"Student message:\n{message}\n\n"
        f"Current local URL:\n{memory.get('last_url') or 'No preview yet.'}\n\n"
        f"Recent memory:\n{recent or 'No previous actions.'}\n\n"
        f"Current HTML:\n```html\n{current_html[:MAX_HTML_SIZE]}\n```"
    )
    reply = call_ai(system, user, temperature=0.25, language=language)
    updated = _append_memory(prompt=message, note="chat", html=html)
    return jsonify({"success": True, "reply": reply, "memory": updated})


@app.route("/generate-code", methods=["POST"])
def generate_code():
    body = safejson()
    prompt = str(body.get("prompt") or body.get("task") or "").strip()
    current_html = str(body.get("code") or body.get("html") or body.get("current_html") or "")
    language = str(body.get("language") or "en")

    if not prompt:
        return jsonify({"success": False, "error": "Prompt cannot be empty", "code": ""}), 400
    if len(prompt) > MAX_MESSAGE_SIZE or len(current_html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": "Request too large", "code": ""}), 413

    memory = _load_html_memory()
    system = (
        "You are CodeUp HTML's website generator for blind school students. "
        "Return one complete accessible single-file HTML document with embedded CSS and small JavaScript only when useful. "
        "Use semantic landmarks, headings, labels, readable contrast, responsive layout, and clear visible content. "
        "Do not return markdown fences or explanations."
    )
    user = (
        f"Build request:\n{prompt}\n\n"
        f"Existing HTML, if this is an edit:\n```html\n{(current_html or memory.get('last_html', ''))[:MAX_HTML_SIZE]}\n```"
    )
    raw = call_ai(system, user, temperature=0.35, language=language)
    if raw.startswith("AI service"):
        return jsonify({"success": False, "error": raw, "code": ""})
    html = _extract_html(raw)
    _append_memory(prompt=prompt, note="Generated website", html=html)
    return jsonify({"success": True, "code": html, "language": "html"})


@app.route("/analyze", methods=["POST"])
def analyze():
    body = safejson()
    html = str(body.get("code") or body.get("html") or "")
    language = str(body.get("language") or "en")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413
    system = (
        "Explain this HTML website to a blind beginner. Describe what it looks like, its sections, "
        "how a visitor would move through it, and one or two accessibility improvements."
    )
    explanation = call_ai(system, f"```html\n{html[:MAX_HTML_SIZE]}\n```", temperature=0.2, language=language)
    _append_memory(note="Explained website", html=html)
    return jsonify({"success": True, "analysis": explanation, "explanation": explanation})


@app.route("/fix", methods=["POST"])
def fix():
    body = safejson()
    html = str(body.get("code") or body.get("html") or "")
    language = str(body.get("language") or "en")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty", "code": ""}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)", "code": ""}), 413
    system = (
        "You are an expert accessibility-focused HTML/CSS/JavaScript reviewer. "
        "Return a complete improved single-file HTML document. Fix accessibility, layout, responsiveness, and clarity. "
        "Do not return markdown fences or prose."
    )
    raw = call_ai(system, f"```html\n{html[:MAX_HTML_SIZE]}\n```", temperature=0.2, language=language)
    if raw.startswith("AI service"):
        return jsonify({"success": False, "error": raw, "code": ""})
    fixed = _extract_html(raw)
    _append_memory(note="Polished HTML", html=fixed)
    return jsonify({"success": True, "code": fixed, "language": "html"})


@app.route("/voice-command", methods=["POST"])
def voice_command():
    text = str(safejson().get("text") or "").strip()
    lower = text.lower()
    if not text:
        return jsonify({"success": True, "action": "unknown", "message": "No command heard"})
    if "pause voice" in lower:
        action = "pause_voice"
    elif "resume voice" in lower or "voice on" in lower:
        action = "resume_voice"
    elif "stop speaking" in lower or "quiet" in lower:
        action = "stop_speaking"
    elif "preview" in lower or "show website" in lower:
        action = "preview_site"
    elif "explain" in lower or "describe" in lower:
        action = "explain_site"
    elif "sonify" in lower or "sound" in lower:
        action = "sonify_site"
    elif re.search(r"\b(build|make|create|generate)\b.*\b(website|site|page)\b", lower):
        action = "build_site"
    else:
        action = "chat"
    return jsonify({"success": True, "action": action, "text": text})


if __name__ == "__main__":
    app.run(debug=True)
