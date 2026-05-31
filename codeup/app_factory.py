from __future__ import annotations

from datetime import timedelta

from flask import Flask

from codeup.config import (
    SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_MAX_AGE,
    SESSION_COOKIE_NAME,
    load_secret_key,
    session_cookie_samesite,
    session_cookie_secure,
)
from codeup.logging import setup_logging
from codeup.routes import ALL_BLUEPRINTS
from codeup.security import register_security_middleware
from codeup.storage import init_data_dirs


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    app.secret_key = load_secret_key()
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=SESSION_COOKIE_MAX_AGE),
        SESSION_COOKIE_NAME=SESSION_COOKIE_NAME,
        SESSION_COOKIE_SECURE=session_cookie_secure(),
        SESSION_COOKIE_HTTPONLY=SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=session_cookie_samesite(),
    )

    setup_logging(app)
    register_security_middleware(app)
    init_data_dirs()

    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)

    return app
