"""Application configuration and environment helpers."""

from __future__ import annotations

import os

__version__ = "1.0.0-html"

DEV_SECRET_KEY = "dev-secret-key-change-in-production"
SESSION_COOKIE_NAME = "codeup_html_session"
SESSION_COOKIE_MAX_AGE = 3600 * 24 * 7
SESSION_COOKIE_HTTPONLY = True

MAX_REQUEST_SIZE = 1_000_000
MAX_HTML_SIZE = 100_000
MAX_MESSAGE_SIZE = 20_000
MAX_MEMORY_ENTRIES = 100
MEMORY_TYPES = {"fact", "instruction", "context"}

AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "30"))
AI_MAX_CONCURRENT = int(os.environ.get("AI_MAX_CONCURRENT", "3"))

DATA_DIR = os.environ.get("DATA_DIR", ".")

SESSION_ARTIFACT_MAX_AGE_SECONDS = int(os.environ.get("SESSION_ARTIFACT_MAX_AGE", str(7 * 24 * 3600)))


def env_enabled(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def production_mode() -> bool:
    return os.environ.get("CODEUP_ENV", "").strip().lower() == "production"


def load_secret_key() -> str:
    secret = os.environ.get("FLASK_SECRET_KEY")
    if secret:
        return secret
    if production_mode():
        raise RuntimeError("FLASK_SECRET_KEY is required when CODEUP_ENV=production.")
    return DEV_SECRET_KEY


def session_cookie_secure() -> bool:
    if "SESSION_COOKIE_SECURE" in os.environ:
        return env_enabled("SESSION_COOKIE_SECURE")
    return production_mode()


def session_cookie_samesite() -> str | None:
    if os.environ.get("FLASK_TESTING", "false").lower() == "true":
        return None
    return "Lax"


def cloud_ai_enabled() -> bool:
    if "AI_CLOUD_ENABLED" in os.environ:
        return env_enabled("AI_CLOUD_ENABLED", default=True)
    return env_enabled("GEMINI_ENABLED", default=True)


def testing_mode() -> bool:
    return env_enabled("FLASK_TESTING")


def flask_debug_enabled() -> bool:
    return env_enabled("FLASK_DEBUG")


ALLOWED_ORIGINS: set[str] = {
    origin.strip().lower() for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",") if origin.strip()
}
