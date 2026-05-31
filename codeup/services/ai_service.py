from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor

from codeup.config import AI_MAX_CONCURRENT, AI_TIMEOUT, cloud_ai_enabled

_ai_executor = ThreadPoolExecutor(max_workers=AI_MAX_CONCURRENT, thread_name_prefix="codeup-ai")
_ai_semaphore = threading.BoundedSemaphore(AI_MAX_CONCURRENT)


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
    if not cloud_ai_enabled():
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

    if not _ai_semaphore.acquire(blocking=False):
        local = _call_ollama(system_prompt, user_prompt, temperature)
        return local or "AI service is busy. Please try again in a moment."

    def run_call() -> str:
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
            _ai_semaphore.release()

    try:
        future = _ai_executor.submit(run_call)
    except Exception:
        _ai_semaphore.release()
        raise
    try:
        return future.result(timeout=AI_TIMEOUT + 1)
    except Exception as exc:
        local = _call_ollama(system_prompt, user_prompt, temperature)
        return local or f"AI service had a problem: {str(exc)[:120]}"


def is_ai_unavailable(reply: str) -> bool:
    lowered = (reply or "").lower()
    return any(
        phrase in lowered
        for phrase in (
            "rate limit",
            "quota",
            "service unavailable",
            "service disabled",
            "service is busy",
            "temporarily unavailable",
            "timed out",
            "not configured",
            "api key",
            "had a problem",
        )
    )
