from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from codeup.app_factory import create_app
from codeup.config import (
    AI_MAX_CONCURRENT,
    SESSION_COOKIE_NAME,
    __version__,
)
from codeup.config import (
    flask_debug_enabled as _flask_debug_enabled,
)
from codeup.services.ai_service import (
    _call_ollama,
    call_ai,
)
from codeup.services.ai_service import (
    is_ai_unavailable as _is_ai_unavailable,
)

app = create_app()

if __name__ == "__main__":
    app.run(debug=_flask_debug_enabled())
