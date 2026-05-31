from __future__ import annotations

import json

from flask import Blueprint, Response, jsonify, stream_with_context

from codeup.config import AI_TIMEOUT, MAX_HTML_SIZE, MAX_MESSAGE_SIZE, cloud_ai_enabled
from codeup.routes.helpers import safejson
from codeup.security import get_session_id
from codeup.services.ai_service import call_ai, is_ai_unavailable
from codeup.services.fallbacks import (
    fallback_apply_review,
    fallback_chat,
    fallback_explanation,
    fallback_review,
)
from codeup.services.html_utils import extract_html, fallback_site, summarize_html_changes, wrap_html
from codeup.services.memory_service import build_context, store_smart_memory
from codeup.storage import append_memory, create_project_version, load_html_memory

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/review-site", methods=["POST"])
def review_site():
    body = safejson()
    html = str(body.get("html") or body.get("code") or "")
    language = str(body.get("language") or "en")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty"}), 400
    if len(html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": f"HTML too large (max {MAX_HTML_SIZE} bytes)"}), 413

    from codeup.services.html_utils import audit_html

    audit = audit_html(html)
    system = (
        "You are the sighted reviewer inside CodeUp HTML for blind and visually impaired students. "
        "Describe the current website visually, then say what is missing, then suggest exactly what to add next. "
        "Keep it conversational, concrete, and short enough to be spoken aloud. Do not return code."
    )
    user = (
        f"Accessibility audit score: {audit.score}/100\n"
        f"Audit suggestions: {', '.join(audit.suggestions)}\n\n"
        f"Current HTML:\n```html\n{html[:MAX_HTML_SIZE]}\n```"
    )
    review = call_ai(system, user, temperature=0.25, language=language)
    if is_ai_unavailable(review):
        review = fallback_review(html, language)
    session_id = get_session_id()
    memory = append_memory(session_id, note=f"Review loop score {audit.score}", html=html, review=review)
    return jsonify({"success": True, "review": review, "audit": audit.to_dict(), "memory": memory})


@ai_bp.route("/apply-review", methods=["POST"])
def apply_review():
    body = safejson()
    html = str(body.get("html") or body.get("code") or "")
    instruction = str(body.get("instruction") or "Apply the latest review suggestions").strip()
    review = str(body.get("review") or "")
    language = str(body.get("language") or "en")
    if not html.strip():
        return jsonify({"success": False, "error": "HTML cannot be empty", "code": ""}), 400
    if len(html) > MAX_HTML_SIZE or len(instruction) > MAX_MESSAGE_SIZE or len(review) > MAX_MESSAGE_SIZE:
        return jsonify({"success": False, "error": "Request too large", "code": ""}), 413

    session_id = get_session_id()
    project_id = str(body.get("project_id") or "").strip()
    memory = load_html_memory(session_id)
    latest_review = review or memory.last_review
    system = (
        "You are CodeUp HTML's review-loop editor. Return one complete accessible single-file HTML document. "
        "Apply the student's instruction using the latest visual review. Keep the page semantic, responsive, "
        "high contrast, and understandable for screen reader users. Do not return markdown fences or prose."
    )
    user = (
        f"Student instruction:\n{instruction}\n\n"
        f"Latest review:\n{latest_review or 'No review yet. Add useful next steps and accessibility improvements.'}\n\n"
        f"Current HTML:\n```html\n{html[:MAX_HTML_SIZE]}\n```"
    )
    raw = call_ai(system, user, temperature=0.25, language=language)
    fixed = fallback_apply_review(html, instruction, latest_review) if is_ai_unavailable(raw) else extract_html(raw)
    summary = summarize_html_changes(html, fixed)
    mem = append_memory(session_id, prompt=instruction, note="Applied review suggestions", html=fixed)
    if project_id:
        create_project_version(
            project_id,
            label="Applied review suggestions",
            source="review-edit",
            html=fixed,
            summary=summary,
        )
    return jsonify({"success": True, "code": fixed, "language": "html", "memory": mem, "summary": summary})


@ai_bp.route("/html-chat", methods=["POST"])
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

    session_id = get_session_id()
    memory = load_html_memory(session_id)
    current_html = html or memory.last_html
    recent = "\n".join(
        f"- {item.get('prompt') or item.get('note')}" for item in memory.history[-8:] if isinstance(item, dict)
    )
    system = (
        "You are CodeUp HTML, a conversational website-building guide for blind and visually impaired students. "
        "Explain what students can do, describe the current page, suggest improvements, and keep responses short enough for speech. "
        "Do not return code from chat; for building, tell the student to say or type 'Build a website for ...'."
    )
    user = (
        f"Student message:\n{message}\n\n"
        f"Current local URL:\n{memory.last_url or 'No preview yet.'}\n\n"
        f"Recent memory:\n{recent or 'No previous actions.'}\n\n"
        f"Current HTML:\n```html\n{current_html[:MAX_HTML_SIZE]}\n```"
    )
    reply = call_ai(system, user, temperature=0.25, language=language)
    if is_ai_unavailable(reply):
        reply = fallback_chat(message, current_html, language)
    updated = append_memory(session_id, prompt=message, note="chat", html=html)
    return jsonify({"success": True, "reply": reply, "memory": updated})


@ai_bp.route("/generate-code", methods=["POST"])
def generate_code():
    body = safejson()
    prompt = str(body.get("prompt") or body.get("task") or "").strip()
    current_html = str(body.get("code") or body.get("html") or body.get("current_html") or "")
    language = str(body.get("language") or "en")
    project_id = str(body.get("project_id") or "").strip()

    if not prompt:
        return jsonify({"success": False, "error": "Prompt cannot be empty", "code": ""}), 400
    if len(prompt) > MAX_MESSAGE_SIZE or len(current_html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": "Request too large", "code": ""}), 413

    session_id = get_session_id()
    memory = load_html_memory(session_id)
    system = (
        "You are CodeUp HTML's website generator for blind school students. "
        "Return one complete accessible single-file HTML document with embedded CSS and small JavaScript only when useful. "
        "Use semantic landmarks, headings, labels, readable contrast, responsive layout, and clear visible content. "
        "Do not return markdown fences or explanations."
    )
    user = (
        f"Build request:\n{prompt}\n\n"
        f"Existing HTML, if this is an edit:\n```html\n{(current_html or memory.last_html)[:MAX_HTML_SIZE]}\n```"
    )
    raw = call_ai(system, user, temperature=0.35, language=language)
    html = fallback_site(prompt) if is_ai_unavailable(raw) else extract_html(raw)
    previous = current_html or memory.last_html
    summary = summarize_html_changes(previous, html)
    append_memory(session_id, prompt=prompt, note="Generated website", html=html)
    if project_id:
        create_project_version(project_id, label="Generated website", source="generate", html=html, summary=summary)
    return jsonify({"success": True, "code": html, "language": "html", "summary": summary})


@ai_bp.route("/analyze", methods=["POST"])
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
    if is_ai_unavailable(explanation):
        explanation = fallback_explanation(html, language)
    session_id = get_session_id()
    append_memory(session_id, note="Explained website", html=html)
    return jsonify({"success": True, "analysis": explanation, "explanation": explanation})


@ai_bp.route("/fix", methods=["POST"])
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
    fixed = wrap_html(html) if is_ai_unavailable(raw) else extract_html(raw)
    session_id = get_session_id()
    summary = summarize_html_changes(html, fixed)
    append_memory(session_id, note="Polished HTML", html=fixed)
    project_id = str(body.get("project_id") or "").strip()
    if project_id:
        create_project_version(project_id, label="Polished HTML", source="polish", html=fixed, summary=summary)
    return jsonify({"success": True, "code": fixed, "language": "html", "summary": summary})


@ai_bp.route("/generate-code-stream", methods=["POST"])
def generate_code_stream():
    body = safejson()
    prompt = str(body.get("prompt") or body.get("task") or "").strip()
    current_html = str(body.get("code") or body.get("html") or body.get("current_html") or "")
    language = str(body.get("language") or "en")
    project_id = str(body.get("project_id") or "").strip()

    if not prompt:
        return jsonify({"success": False, "error": "Prompt cannot be empty"}), 400
    if len(prompt) > MAX_MESSAGE_SIZE or len(current_html) > MAX_HTML_SIZE:
        return jsonify({"success": False, "error": "Request too large"}), 413

    session_id = get_session_id()
    context = build_context(session_id, prompt)

    memory = load_html_memory(session_id)
    system = (
        "You are CodeUp HTML's website generator for blind school students. "
        "Return one complete accessible single-file HTML document with embedded CSS and small JavaScript only when useful. "
        "Use semantic landmarks, headings, labels, readable contrast, responsive layout, and clear visible content. "
        "Do not return markdown fences or explanations."
    )
    if context:
        system += f"\n\nContext from previous interactions:\n{context}"

    user = (
        f"Build request:\n{prompt}\n\n"
        f"Existing HTML, if this is an edit:\n```html\n{(current_html or memory.last_html)[:MAX_HTML_SIZE]}\n```"
    )

    import os

    from codeup.services.ai_service import _ai_semaphore

    def generate():
        if not cloud_ai_enabled():
            fallback = fallback_site(prompt)
            yield f"data: {json.dumps({'chunk': fallback, 'done': True})}\n\n"
            store_smart_memory(session_id, f"Built website: {prompt}", "instruction")
            append_memory(session_id, prompt=prompt, note="Generated website (stream)", html=fallback)
            return

        xai_key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
        groq_key = os.environ.get("GROQ_API_KEY")
        if not xai_key and not groq_key:
            fallback = fallback_site(prompt)
            yield f"data: {json.dumps({'chunk': fallback, 'done': True})}\n\n"
            store_smart_memory(session_id, f"Built website: {prompt}", "instruction")
            append_memory(session_id, prompt=prompt, note="Generated website (stream)", html=fallback)
            return

        if not _ai_semaphore.acquire(blocking=False):
            fallback = fallback_site(prompt)
            yield f"data: {json.dumps({'chunk': fallback, 'done': True})}\n\n"
            append_memory(session_id, prompt=prompt, note="Generated website (stream-busy)", html=fallback)
            return

        full_response = ""
        try:
            import requests as req_lib

            if xai_key:
                resp = req_lib.post(
                    os.environ.get("XAI_API_URL", "https://api.x.ai/v1/chat/completions"),
                    headers={"Authorization": f"Bearer {xai_key}", "Content-Type": "application/json"},
                    json={
                        "model": os.environ.get("XAI_MODEL", os.environ.get("GROK_MODEL", "grok-3-mini")),
                        "messages": [
                            {
                                "role": "system",
                                "content": system
                                if language != "hi"
                                else f"Reply in natural Hindi or Hinglish for a blind student. {system}",
                            },
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0.35,
                        "max_tokens": 4096,
                        "stream": True,
                    },
                    timeout=AI_TIMEOUT,
                    stream=True,
                )
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(payload)
                        delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_response += content
                            yield f"data: {json.dumps({'chunk': content, 'done': False})}\n\n"
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue
            else:
                from groq import Groq

                stream = Groq(api_key=groq_key).chat.completions.create(
                    model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    messages=[
                        {
                            "role": "system",
                            "content": system
                            if language != "hi"
                            else f"Reply in natural Hindi or Hinglish for a blind student. {system}",
                        },
                        {"role": "user", "content": user},
                    ],
                    temperature=0.35,
                    max_tokens=4096,
                    stream=True,
                )
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_response += content
                        yield f"data: {json.dumps({'chunk': content, 'done': False})}\n\n"
        except Exception:
            if not full_response:
                fallback = fallback_site(prompt)
                yield f"data: {json.dumps({'chunk': fallback, 'done': True})}\n\n"
                append_memory(session_id, prompt=prompt, note="Generated website (stream-fallback)", html=fallback)
                return
        finally:
            _ai_semaphore.release()

        html = extract_html(full_response) if full_response else fallback_site(prompt)
        summary = summarize_html_changes(current_html or memory.last_html, html)
        if project_id:
            create_project_version(
                project_id, label="Generated website (stream)", source="generate-stream", html=html, summary=summary
            )
        yield f"data: {json.dumps({'done': True, 'html': html, 'summary': summary})}\n\n"
        store_smart_memory(session_id, f"Built website: {prompt}", "instruction")
        append_memory(session_id, prompt=prompt, note="Generated website (stream)", html=html)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
