from __future__ import annotations

import logging
import uuid

from flask import g, has_request_context, request


class RequestContextFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            record.request_id = getattr(g, "request_id", "-")
            record.session_id = getattr(g, "session_id", "-")
        else:
            record.request_id = "-"
            record.session_id = "-"
        return True


def setup_logging(app) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s req=%(request_id)s sess=%(session_id)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(RequestContextFilter())

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    @app.before_request
    def _assign_request_id():
        g.request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
