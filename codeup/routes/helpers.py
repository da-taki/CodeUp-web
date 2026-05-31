from __future__ import annotations

from typing import Any

from flask import request


def safejson() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}
