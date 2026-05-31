"""Tests for the storage abstraction layer and cleanup logic."""

import os
import time

import pytest


@pytest.fixture(autouse=True)
def _patch_data_dir(monkeypatch, tmp_path):
    import codeup.config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path))
    return tmp_path


class TestHtmlMemory:
    def test_load_returns_empty_memory_when_no_file(self, tmp_path):
        from codeup.storage import load_html_memory

        memory = load_html_memory("nonexistent-session")
        assert memory.history == []
        assert memory.last_html == ""
        assert memory.last_url == ""

    def test_save_and_load_roundtrip(self, tmp_path):
        from codeup.models import HtmlMemory
        from codeup.storage import load_html_memory, save_html_memory

        mem = HtmlMemory(
            history=[{"prompt": "test", "note": "n", "url": "", "timestamp": 1.0}],
            last_html="<h1>Test</h1>",
            last_url="/test/",
        )
        save_html_memory(mem, "test-session")
        loaded = load_html_memory("test-session")
        assert loaded.last_html == "<h1>Test</h1>"
        assert loaded.last_url == "/test/"
        assert len(loaded.history) == 1

    def test_save_trims_history_to_30(self, tmp_path):
        from codeup.models import HtmlMemory
        from codeup.storage import load_html_memory, save_html_memory

        mem = HtmlMemory(
            history=[{"prompt": f"p{i}", "note": "", "url": "", "timestamp": float(i)} for i in range(50)],
        )
        save_html_memory(mem, "trim-test")
        loaded = load_html_memory("trim-test")
        assert len(loaded.history) == 30

    def test_append_memory_creates_entry(self, tmp_path):
        from codeup.storage import append_memory, load_html_memory

        result = append_memory("sess1", prompt="hello", note="test")
        assert len(result["history"]) == 1
        assert result["history"][0]["prompt"] == "hello"

        loaded = load_html_memory("sess1")
        assert len(loaded.history) == 1


class TestStudentSites:
    def test_write_and_read_student_page(self, tmp_path):
        from codeup.storage import student_site_path, write_student_page

        write_student_page("s1", "index.html", "<h1>Hello</h1>")
        path = os.path.join(student_site_path("s1"), "index.html")
        assert os.path.exists(path)
        with open(path) as f:
            assert "<h1>Hello</h1>" in f.read()

    def test_delete_stale_pages(self, tmp_path):
        from codeup.storage import delete_stale_hosted_pages, write_student_page

        write_student_page("s2", "index.html", "<h1>Home</h1>")
        write_student_page("s2", "about.html", "<h1>About</h1>")
        delete_stale_hosted_pages("s2", {"index.html"})
        from codeup.storage import student_site_path

        assert os.path.exists(os.path.join(student_site_path("s2"), "index.html"))
        assert not os.path.exists(os.path.join(student_site_path("s2"), "about.html"))

    def test_remove_student_site(self, tmp_path):
        from codeup.storage import remove_student_site, student_site_path, write_student_page

        write_student_page("s3", "index.html", "<h1>Bye</h1>")
        assert os.path.isdir(student_site_path("s3"))
        remove_student_site("s3")
        assert not os.path.isdir(student_site_path("s3"))


class TestCleanup:
    def test_cleanup_removes_old_sessions(self, tmp_path, monkeypatch):
        import codeup.config as config_module
        from codeup.models import HtmlMemory
        from codeup.storage import cleanup_expired_sessions, save_html_memory, write_student_page

        monkeypatch.setattr(config_module, "SESSION_ARTIFACT_MAX_AGE_SECONDS", 1)

        save_html_memory(HtmlMemory(last_html="<h1>Old</h1>"), "old-session")
        write_student_page("old-session", "index.html", "<h1>Old</h1>")

        memory_path = os.path.join(tmp_path, "html_memory", "old-session.json")
        old_time = time.time() - 10
        os.utime(memory_path, (old_time, old_time))

        cleaned = cleanup_expired_sessions()
        assert cleaned >= 1
        assert not os.path.exists(memory_path)

    def test_cleanup_keeps_recent_sessions(self, tmp_path, monkeypatch):
        import codeup.config as config_module
        from codeup.models import HtmlMemory
        from codeup.storage import cleanup_expired_sessions, save_html_memory

        monkeypatch.setattr(config_module, "SESSION_ARTIFACT_MAX_AGE_SECONDS", 3600)

        save_html_memory(HtmlMemory(last_html="<h1>Recent</h1>"), "recent-session")

        cleaned = cleanup_expired_sessions()
        assert cleaned == 0
        memory_path = os.path.join(tmp_path, "html_memory", "recent-session.json")
        assert os.path.exists(memory_path)
