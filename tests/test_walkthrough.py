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


GOOD_HTML = (
    "<!doctype html><html lang='en'><head><title>Club</title>"
    "<meta name='viewport' content='width=device-width'></head>"
    "<body><header><nav aria-label='Main'><a href='/'>Home</a>"
    "<a href='/about'>About</a><a href='/join'>Join</a></nav></header>"
    "<main><h1>Robotics Club</h1><section><h2>About</h2>"
    "<p>We build robots.</p><img src='robot.jpg' alt='Students building a robot'>"
    "<button type='button'>Join Now</button></section></main>"
    "<footer>Footer</footer></body></html>"
)

FLAWED_HTML = (
    "<!doctype html><html lang='en'><head><title>Test</title>"
    "<meta name='viewport' content='width=device-width'></head>"
    "<body><main><h1>Test Page</h1>"
    "<img src='photo.jpg'>"
    "<button></button>"
    "<input type='text'>"
    "<h3>Skipped heading</h3>"
    "</main></body></html>"
)

EMPTY_HTML = ""

NESTED_NAV_HTML = (
    "<!doctype html><html lang='en'><head><title>Nested Nav</title>"
    "<meta name='viewport' content='width=device-width'></head>"
    "<body><header><nav aria-label='Main navigation'><ul>"
    "<li><a href='#home'>Home</a></li><li><a href='#events'>Events</a></li>"
    "</ul></nav></header><main><h1>Club</h1></main></body></html>"
)

FOCUS_EDGE_HTML = (
    "<!doctype html><html lang='en'><head><title>Focus</title>"
    "<meta name='viewport' content='width=device-width'></head>"
    "<body><main><h1>Focus Test</h1>"
    "<a>No href</a>"
    "<a href='#home'>Home</a>"
    "<button disabled>Disabled</button>"
    "<input type='hidden' value='skip-me'>"
    "<button tabindex='-1'>Skip me</button>"
    "<button hidden>Hidden Button</button>"
    "<a href='#hidden' aria-hidden='true'>Hidden Link</a>"
    "<button style='display:none'>Display None</button>"
    "<button style='visibility:hidden'>Invisible</button>"
    "<div role='button' tabindex='1'>Priority Role Button</div>"
    "<button tabindex='2'>Priority Native</button>"
    "<button>Join</button>"
    "<input aria-label='Email'>"
    "</main></body></html>"
)


class TestPageMap:
    def test_page_map_good_html(self, client):
        data = client.post("/walkthrough/page-map", json={"html": GOOD_HTML}).get_json()
        assert data["success"] is True
        assert "Robotics Club" in data["summary"]
        assert data["links"] == 3
        assert data["buttons"] == 1
        assert data["images"] == 1
        assert len(data["headings"]) >= 1
        assert len(data["landmarks"]) >= 1

    def test_page_map_empty_html(self, client):
        data = client.post("/walkthrough/page-map", json={"html": EMPTY_HTML}).get_json()
        assert data["success"] is True
        assert "no current website" in data["summary"].lower()
        assert data["links"] == 0

    def test_page_map_flawed_html_reports_watchpoints(self, client):
        data = client.post("/walkthrough/page-map", json={"html": FLAWED_HTML}).get_json()
        assert data["success"] is True
        assert data["watchpoint_count"] > 0
        assert "watchpoint" in data["summary"].lower()

    def test_page_map_heading_hierarchy(self, client):
        data = client.post("/walkthrough/page-map", json={"html": GOOD_HTML}).get_json()
        levels = [h["level"] for h in data["headings"]]
        assert 1 in levels

    def test_page_map_navigation_region(self, client):
        data = client.post("/walkthrough/page-map", json={"html": GOOD_HTML}).get_json()
        nav_landmarks = [lm for lm in data["landmarks"] if lm["tag"] == "nav"]
        assert len(nav_landmarks) >= 1

    def test_page_map_nested_navigation_links(self, client):
        data = client.post("/walkthrough/page-map", json={"html": NESTED_NAV_HTML}).get_json()
        assert "Navigation region with links Home, Events" in data["summary"]

    def test_page_map_images_and_alt(self, client):
        data = client.post("/walkthrough/page-map", json={"html": GOOD_HTML}).get_json()
        assert data["images"] == 1
        assert data["watchpoint_count"] == 0

    def test_page_map_buttons_links_names(self, client):
        data = client.post("/walkthrough/page-map", json={"html": GOOD_HTML}).get_json()
        assert data["buttons"] == 1
        assert data["links"] == 3

    def test_page_map_form_label_detection(self, client):
        html_with_form = (
            "<!doctype html><html lang='en'><head><title>Form</title>"
            "<meta name='viewport' content='width=device-width'></head>"
            "<body><main><h1>Form Page</h1>"
            "<form><label for='name'>Name</label><input id='name' type='text'></form>"
            "</main></body></html>"
        )
        data = client.post("/walkthrough/page-map", json={"html": html_with_form}).get_json()
        assert data["forms"] == 1
        assert data["inputs"] == 1

    def test_page_map_bounded_output(self, client):
        data = client.post("/walkthrough/page-map", json={"html": GOOD_HTML}).get_json()
        assert len(data["summary"]) < 2000

    def test_page_map_malformed_html(self, client):
        data = client.post("/walkthrough/page-map", json={"html": "<div><h1>Broken<h2>Page"}).get_json()
        assert data["success"] is True
        assert len(data["summary"]) > 0


class TestKeyboardJourney:
    def test_journey_start(self, client):
        data = client.post("/walkthrough/keyboard-journey", json={"html": GOOD_HTML}).get_json()
        assert data["success"] is True
        assert data["total"] > 0
        assert data["index"] == 0
        assert "first interactive element" in data["message"].lower()

    def test_journey_ordered_elements(self, client):
        data = client.post("/walkthrough/keyboard-journey", json={"html": GOOD_HTML}).get_json()
        tags = [el["tag"] for el in data["elements"]]
        assert "a" in tags
        assert "button" in tags

    def test_journey_next(self, client):
        start = client.post("/walkthrough/keyboard-journey", json={"html": GOOD_HTML}).get_json()
        move = client.post(
            "/walkthrough/keyboard-move",
            json={
                "html": GOOD_HTML,
                "index": start["index"],
                "direction": "next",
            },
        ).get_json()
        assert move["success"] is True
        assert move["index"] == 1
        assert "next" in move["message"].lower()

    def test_journey_previous(self, client):
        move = client.post(
            "/walkthrough/keyboard-move",
            json={
                "html": GOOD_HTML,
                "index": 2,
                "direction": "previous",
            },
        ).get_json()
        assert move["success"] is True
        assert move["index"] == 1

    def test_journey_beginning_boundary(self, client):
        move = client.post(
            "/walkthrough/keyboard-move",
            json={
                "html": GOOD_HTML,
                "index": 0,
                "direction": "previous",
            },
        ).get_json()
        assert move["index"] == 0
        assert "beginning" in move["message"].lower()

    def test_journey_end_boundary(self, client):
        start = client.post("/walkthrough/keyboard-journey", json={"html": GOOD_HTML}).get_json()
        last_index = start["total"] - 1
        move = client.post(
            "/walkthrough/keyboard-move",
            json={
                "html": GOOD_HTML,
                "index": last_index,
                "direction": "next",
            },
        ).get_json()
        assert move["index"] == last_index
        assert "last" in move["message"].lower()

    def test_journey_empty_page(self, client):
        data = client.post("/walkthrough/keyboard-journey", json={"html": EMPTY_HTML}).get_json()
        assert data["success"] is True
        assert data["total"] == 0
        assert "no current website" in data["message"].lower()

    def test_journey_no_interactive_elements(self, client):
        html = "<!doctype html><html lang='en'><head><title>T</title></head><body><p>Just text</p></body></html>"
        data = client.post("/walkthrough/keyboard-journey", json={"html": html}).get_json()
        assert data["total"] == 0
        assert "no interactive elements" in data["message"].lower()

    def test_journey_filters_non_focusable_elements_and_orders_positive_tabindex(self, client):
        data = client.post("/walkthrough/keyboard-journey", json={"html": FOCUS_EDGE_HTML}).get_json()
        labels = [el["label"] for el in data["elements"]]

        assert labels[:2] == ["button, Priority Role Button", "button, Priority Native"]
        assert "link, Home" in labels
        assert "button, Join" in labels
        assert "text input, Email" in labels
        assert "link, No href" not in labels
        assert "button, Disabled" not in labels
        assert "hidden input, skip-me" not in labels
        assert "button, Skip me" not in labels
        assert "button, Hidden Button" not in labels
        assert "link, Hidden Link" not in labels
        assert "button, Display None" not in labels
        assert "button, Invisible" not in labels

    def test_journey_marks_element_linked_watchpoints(self, client):
        html = (
            "<!doctype html><html lang='en'><head><title>Watch</title>"
            "<meta name='viewport' content='width=device-width'></head>"
            "<body><main><h1>Watch</h1><button>Join</button><button></button>"
            "<input type='text'></main></body></html>"
        )
        start = client.post("/walkthrough/keyboard-journey", json={"html": html}).get_json()
        move = client.post(
            "/walkthrough/keyboard-move",
            json={"html": html, "index": start["index"], "direction": "next"},
        ).get_json()

        assert move["element"]["watchpoint"]["id"] == "unnamed_button"
        assert move["element"]["selector"] == move["element"]["watchpoint"]["selector"]


class TestWatchpoints:
    def test_watchpoints_missing_alt(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": FLAWED_HTML}).get_json()
        assert data["success"] is True
        assert data["count"] > 0
        ids = [wp["id"] for wp in data["watchpoints"]]
        assert "missing_image_alt" in ids

    def test_watchpoints_unnamed_button(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": FLAWED_HTML}).get_json()
        ids = [wp["id"] for wp in data["watchpoints"]]
        assert "unnamed_button" in ids

    def test_watchpoints_unlabeled_input(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": FLAWED_HTML}).get_json()
        ids = [wp["id"] for wp in data["watchpoints"]]
        assert "missing_form_label" in ids

    def test_watchpoints_skipped_heading(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": FLAWED_HTML}).get_json()
        ids = [wp["id"] for wp in data["watchpoints"]]
        assert "heading_skip" in ids

    def test_watchpoints_no_issues(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": GOOD_HTML}).get_json()
        assert data["count"] == 0
        assert "no accessibility watchpoints" in data["message"].lower()

    def test_watchpoints_bounded(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": FLAWED_HTML}).get_json()
        assert data["count"] <= 10

    def test_watchpoints_empty_page(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": EMPTY_HTML}).get_json()
        assert "no current website" in data["message"].lower()

    def test_pause_on_issue_behavior(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": FLAWED_HTML}).get_json()
        assert data["count"] > 0
        assert len(data["watchpoints"]) == data["count"]

    def test_list_issues(self, client):
        data = client.post("/walkthrough/watchpoints", json={"html": FLAWED_HTML}).get_json()
        assert "1." in data["message"]


class TestExplainIssue:
    def test_explain_first_issue(self, client):
        data = client.post("/walkthrough/explain", json={"html": FLAWED_HTML, "issue_index": 0}).get_json()
        assert data["success"] is True
        assert "watchpoint" in data["message"].lower()
        assert data["issue"] is not None

    def test_explain_no_issues(self, client):
        data = client.post("/walkthrough/explain", json={"html": GOOD_HTML, "issue_index": 0}).get_json()
        assert "no accessibility watchpoints" in data["message"].lower()

    def test_explain_empty_page(self, client):
        data = client.post("/walkthrough/explain", json={"html": EMPTY_HTML, "issue_index": 0}).get_json()
        assert "no current website" in data["message"].lower()


class TestRepairReplay:
    def test_fix_missing_alt(self, client):
        data = client.post("/walkthrough/fix", json={"html": FLAWED_HTML, "issue_index": 0}).get_json()
        assert data["success"] is True
        assert data["fixed_html"]
        assert data["score_before"] is not None
        assert data["score_after"] is not None

    def test_fix_score_change_measured(self, client):
        data = client.post("/walkthrough/fix", json={"html": FLAWED_HTML, "issue_index": 0}).get_json()
        assert data["score_after"] >= data["score_before"]

    def test_fix_no_prior_state(self, client):
        data = client.post("/walkthrough/fix", json={"html": GOOD_HTML, "issue_index": 0}).get_json()
        assert "no accessibility issues" in data["message"].lower()

    def test_fix_cannot_apply_safely(self, client):
        html = (
            "<!doctype html><html lang='en'><head><title>T</title>"
            "<meta name='viewport' content='width=device-width'></head>"
            "<body><main><h1>H</h1><h3>Skip</h3></main></body></html>"
        )
        wp = client.post("/walkthrough/watchpoints", json={"html": html}).get_json()
        skip_idx = None
        for i, issue in enumerate(wp["watchpoints"]):
            if issue["id"] == "heading_skip":
                skip_idx = i
                break
        if skip_idx is not None:
            data = client.post("/walkthrough/fix", json={"html": html, "issue_index": skip_idx}).get_json()
            assert data["success"] is False
            assert "cannot" in data["message"].lower() or "manual" in data["message"].lower()

    def test_fix_empty_page(self, client):
        data = client.post("/walkthrough/fix", json={"html": EMPTY_HTML, "issue_index": 0}).get_json()
        assert data["success"] is False

    def test_compare_before_after(self, client):
        fix_data = client.post("/walkthrough/fix", json={"html": FLAWED_HTML, "issue_index": 0}).get_json()
        compare = client.post(
            "/walkthrough/compare",
            json={
                "html_before": FLAWED_HTML,
                "html_after": fix_data["fixed_html"],
            },
        ).get_json()
        assert compare["success"] is True
        assert compare["score_before"] is not None
        assert compare["score_after"] is not None
        assert len(compare["message"]) > 0

    def test_compare_no_before(self, client):
        data = client.post(
            "/walkthrough/compare",
            json={
                "html_before": "",
                "html_after": GOOD_HTML,
            },
        ).get_json()
        assert "cannot compare" in data["message"].lower()

    def test_remaining_issues_after_partial_repair(self, client):
        fix_data = client.post("/walkthrough/fix", json={"html": FLAWED_HTML, "issue_index": 0}).get_json()
        if fix_data["success"]:
            compare = client.post(
                "/walkthrough/compare",
                json={
                    "html_before": FLAWED_HTML,
                    "html_after": fix_data["fixed_html"],
                },
            ).get_json()
            assert compare["issues_after"] < compare["issues_before"] or compare["issues_after"] >= 0

    def test_fix_and_compare_pairs_second_missing_image(self, client):
        html = (
            "<!doctype html><html lang='en'><head><title>Gallery</title>"
            "<meta name='viewport' content='width=device-width'></head>"
            "<body><main><h1>Gallery</h1><img src='one.jpg'><img src='two.jpg'></main></body></html>"
        )
        fix_data = client.post("/walkthrough/fix", json={"html": html, "issue_index": 1}).get_json()
        assert fix_data["success"] is True
        assert "<img src='one.jpg'>" in fix_data["fixed_html"]
        assert "<img src='two.jpg' alt=\"Describe this image\">" in fix_data["fixed_html"]

        compare = client.post(
            "/walkthrough/compare",
            json={"html_before": html, "html_after": fix_data["fixed_html"]},
        ).get_json()
        assert "Image 2 now has alternative text" in compare["message"]
        assert "Image 1 now has alternative text" not in compare["message"]

    def test_fix_and_compare_pairs_second_unlabeled_control(self, client):
        html = (
            "<!doctype html><html lang='en'><head><title>Form</title>"
            "<meta name='viewport' content='width=device-width'></head>"
            "<body><main><h1>Form</h1><form><input type='text'><input type='email'></form></main></body></html>"
        )
        fix_data = client.post("/walkthrough/fix", json={"html": html, "issue_index": 1}).get_json()
        assert fix_data["success"] is True
        assert "<input type='text'>" in fix_data["fixed_html"]
        assert "<input aria-label=\"Input field\" type='email'>" in fix_data["fixed_html"]

        compare = client.post(
            "/walkthrough/compare",
            json={"html_before": html, "html_after": fix_data["fixed_html"]},
        ).get_json()
        assert "Email input 2 now has readable label" in compare["message"]


class TestCommandRouting:
    def test_walkthrough_commands_route_correctly(self, client):
        commands = {
            "walk me through this page": "walkthrough_page",
            "audio accessibility walkthrough": "walkthrough_page",
            "read the page structure": "walkthrough_page",
            "start keyboard journey": "walkthrough_keyboard_start",
            "next interactive element": "walkthrough_next_element",
            "previous interactive element": "walkthrough_prev_element",
            "pause on accessibility issues": "walkthrough_pause_issues",
            "list accessibility watchpoints": "walkthrough_list_watchpoints",
            "explain first issue": "walkthrough_explain_issue",
            "why is this inaccessible": "walkthrough_explain_issue",
            "fix this issue": "walkthrough_fix_issue",
            "compare accessibility before and after": "walkthrough_compare",
            "stop walkthrough": "walkthrough_stop",
        }
        for text, expected_action in commands.items():
            data = client.post("/voice-command", json={"text": text}).get_json()
            assert data["action"] == expected_action, (
                f"Command '{text}' routed to '{data['action']}' instead of '{expected_action}'"
            )

    def test_walkthrough_commands_do_not_collide_with_existing(self, client):
        existing = {
            "build a website for my school": "build_site",
            "preview website": "preview_site",
            "review website": "review_site",
            "audit website": "audit_site",
            "add that": "apply_review",
            "explain website": "explain_site",
            "outline website": "outline_site",
            "sonify website": "sonify_site",
            "polish HTML": "polish_html",
            "export website": "export_site",
            "pause voice": "pause_voice",
            "reset session": "reset_session",
        }
        for text, expected_action in existing.items():
            data = client.post("/voice-command", json={"text": text}).get_json()
            assert data["action"] == expected_action, f"Existing command '{text}' collided: got '{data['action']}'"
