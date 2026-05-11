# tests/conftest.py
import pytest


@pytest.fixture(autouse=True)
def enable_testing_mode(tmp_path, monkeypatch):
    """Disable SameSite on session cookie so Flask test client sends it back.
    Also redirect snippet storage to a temp directory so per-session
    snippet files don't pollute the working directory during tests, and
    shrink rate-limit window so rate-limit tests don't take 60s+.
    """
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app as app_module
    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    # Shrink rate-limit window for fast, reliable tests
    monkeypatch.setattr(app_module, "RUN_RATE_WINDOW", 5)
    yield