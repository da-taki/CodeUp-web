"""Tests for typed domain models."""

from codeup.models import AuditResult, HtmlMemory


class TestHtmlMemory:
    def test_from_dict_with_valid_data(self):
        data = {
            "history": [{"prompt": "test", "note": "n"}],
            "last_html": "<h1>Hi</h1>",
            "last_url": "/test/",
            "last_review": "looks good",
            "smart_memory": [{"type": "fact", "content": "name is Alice"}],
            "_hashes": ["abc123"],
        }
        mem = HtmlMemory.from_dict(data)
        assert mem.last_html == "<h1>Hi</h1>"
        assert len(mem.history) == 1
        assert len(mem.smart_memory) == 1
        assert mem._hashes == ["abc123"]

    def test_from_dict_with_empty_dict(self):
        mem = HtmlMemory.from_dict({})
        assert mem.history == []
        assert mem.last_html == ""

    def test_from_dict_with_invalid_types(self):
        data = {"history": "not a list", "smart_memory": 42}
        mem = HtmlMemory.from_dict(data)
        assert mem.history == []
        assert mem.smart_memory == []

    def test_from_dict_with_non_dict(self):
        mem = HtmlMemory.from_dict("invalid")
        assert mem.history == []

    def test_to_dict_roundtrip(self):
        mem = HtmlMemory(last_html="<p>test</p>", last_url="/x/")
        d = mem.to_dict()
        restored = HtmlMemory.from_dict(d)
        assert restored.last_html == "<p>test</p>"
        assert restored.last_url == "/x/"


class TestAuditResult:
    def test_to_dict(self):
        result = AuditResult(
            score=89,
            passed=8,
            total=9,
            checks=[{"label": "test", "passed": True}],
            issues=["missing title"],
            suggestions=["add title"],
            contrast_pairs=[],
            screen_reader_checks=[],
            screen_reader_transcript=[],
        )
        d = result.to_dict()
        assert d["score"] == 89
        assert d["passed"] == 8
        assert len(d["checks"]) == 1
