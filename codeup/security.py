from __future__ import annotations

import re
import uuid

from flask import Flask, Response, g, jsonify, request, session

from codeup.config import (
    ALLOWED_ORIGINS,
    MAX_REQUEST_SIZE,
    testing_mode,
)


def sanitize_id(value: str | None) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]", "", value or "")[:64]
    return clean or str(uuid.uuid4())


def get_session_id() -> str:
    cached = getattr(g, "session_id", None)
    if cached:
        return cached
    session.permanent = True
    stored = session.get("session_id")
    session_id = sanitize_id(stored if isinstance(stored, str) else None)
    if stored != session_id:
        session["session_id"] = session_id
    g.session_id = session_id
    return session_id


def register_security_middleware(app: Flask) -> None:
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
            if testing_mode():
                return None
            return jsonify({"success": False, "error": "Missing Origin/Referer header"}), 403

        if origin:
            origin_lower = origin.lower()
            origin_host = origin_lower.split("://", 1)[-1]
            if origin_host == host or origin_lower in ALLOWED_ORIGINS:
                return None
            return jsonify({"success": False, "error": "Cross-origin request blocked"}), 403

        if referer:
            from urllib.parse import urlparse

            parsed = urlparse(referer)
            referer_host = parsed.netloc.lower()
            referer_origin = f"{parsed.scheme}://{parsed.netloc}".lower()
            if referer_host == host or referer_origin in ALLOWED_ORIGINS:
                return None
            return jsonify({"success": False, "error": "Cross-origin request blocked"}), 403

        return None

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"

        if request.path.startswith("/student-site/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; "
                "style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; "
                "worker-src 'self'; "
                "img-src 'self' data: blob:; "
                "font-src 'self' data:; "
                "form-action 'none'; "
                "frame-ancestors 'self'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "worker-src 'self'; "
                "img-src 'self' data: blob:; "
                "font-src 'self' data:; "
                "connect-src 'self'; "
                "frame-src 'self'; "
                "frame-ancestors 'self'"
            )

        return response


def sanitize_hosted_html(html: str) -> tuple[str, list[str]] | str:
    warnings: list[str] = []
    external_scripts = re.findall(
        r'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']*)["\'][^>]*>.*?</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    sanitized = re.sub(
        r'<script\b[^>]*\bsrc\s*=\s*["\'][^"\']*["\'][^>]*>.*?</script>',
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for src in external_scripts:
        warnings.append(f"Removed external script: {src}")

    external_stylesheets = re.findall(
        r'<link\b[^>]*\brel\s*=\s*["\']stylesheet["\'][^>]*\bhref\s*=\s*["\'](https?://[^"\']*)["\'][^>]*/?>',
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r'<link\b[^>]*\brel\s*=\s*["\']stylesheet["\'][^>]*\bhref\s*=\s*["\']https?://[^"\']*["\'][^>]*/?>',
        "",
        sanitized,
        flags=re.IGNORECASE,
    )
    for href in external_stylesheets:
        warnings.append(f"Removed external stylesheet: {href}")

    return sanitized, warnings
