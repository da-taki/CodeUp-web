import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module
    import codeup.config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


class TestSecurityHeaders:
    def test_main_page_has_csp_header(self, client):
        response = client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp

    def test_main_page_has_x_content_type_options(self, client):
        response = client.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_main_page_has_x_frame_options(self, client):
        response = client.get("/")
        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_student_site_has_restrictive_csp(self, client):
        client.post("/publish-site", json={"html": "<h1>Test</h1>"})
        response = client.get("/healthz")
        pub = client.post("/publish-site", json={"html": "<h1>Test</h1>"})
        url = pub.get_json()["url"]
        response = client.get(url)
        csp = response.headers.get("Content-Security-Policy", "")
        assert "default-src 'none'" in csp
        assert "form-action 'none'" in csp
        assert "frame-ancestors 'self'" in csp

    def test_student_site_csp_allows_self_images(self, client):
        pub = client.post("/publish-site", json={"html": "<h1>Test</h1>"})
        url = pub.get_json()["url"]
        response = client.get(url)
        csp = response.headers.get("Content-Security-Policy", "")
        assert "'self'" in csp.split("img-src")[1].split(";")[0]

    def test_student_site_csp_allows_self_fonts(self, client):
        pub = client.post("/publish-site", json={"html": "<h1>Test</h1>"})
        url = pub.get_json()["url"]
        response = client.get(url)
        csp = response.headers.get("Content-Security-Policy", "")
        assert "'self'" in csp.split("font-src")[1].split(";")[0]

    def test_referrer_policy_is_set(self, client):
        response = client.get("/")
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


class TestHtmlSanitization:
    def test_external_scripts_are_stripped(self):
        from codeup.security import sanitize_hosted_html

        html = '<html><body><script src="https://evil.com/xss.js"></script><h1>Safe</h1></body></html>'
        result, warnings = sanitize_hosted_html(html)
        assert "evil.com" not in result
        assert "<h1>Safe</h1>" in result
        assert any("evil.com/xss.js" in w for w in warnings)

    def test_inline_scripts_are_preserved(self):
        from codeup.security import sanitize_hosted_html

        html = "<html><body><script>alert('hello')</script></body></html>"
        result, warnings = sanitize_hosted_html(html)
        assert "alert('hello')" in result
        assert warnings == []

    def test_external_stylesheets_are_stripped(self):
        from codeup.security import sanitize_hosted_html

        html = '<html><head><link rel="stylesheet" href="https://evil.com/style.css"></head><body></body></html>'
        result, warnings = sanitize_hosted_html(html)
        assert "evil.com" not in result
        assert any("evil.com/style.css" in w for w in warnings)

    def test_sanitize_returns_warnings_for_each_removed_resource(self):
        from codeup.security import sanitize_hosted_html

        html = (
            "<html><head>"
            '<link rel="stylesheet" href="https://cdn.example.com/a.css">'
            '<link rel="stylesheet" href="https://cdn.example.com/b.css">'
            "</head><body>"
            '<script src="https://cdn.example.com/c.js"></script>'
            "<h1>Content</h1></body></html>"
        )
        result, warnings = sanitize_hosted_html(html)
        assert len(warnings) == 3
        assert "<h1>Content</h1>" in result

    def test_no_warnings_for_clean_html(self):
        from codeup.security import sanitize_hosted_html

        html = "<html><body><h1>Clean</h1><style>body{color:red}</style><script>console.log(1)</script></body></html>"
        result, warnings = sanitize_hosted_html(html)
        assert warnings == []
        assert "<h1>Clean</h1>" in result


class TestSanitizeId:
    def test_strips_special_characters(self):
        from codeup.security import sanitize_id

        assert sanitize_id("abc-123_DEF") == "abc-123_DEF"
        assert sanitize_id("../../../etc/passwd") == "etcpasswd"
        assert sanitize_id("<script>alert(1)</script>") == "scriptalert1script"

    def test_empty_input_generates_uuid(self):
        from codeup.security import sanitize_id

        result = sanitize_id("")
        assert len(result) > 0
        assert result != ""

    def test_none_input_generates_uuid(self):
        from codeup.security import sanitize_id

        result = sanitize_id(None)
        assert len(result) > 0

    def test_truncates_to_64_characters(self):
        from codeup.security import sanitize_id

        result = sanitize_id("a" * 100)
        assert len(result) == 64
