import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module
    import codeup.config as config_module
    import codeup.services.python_learning as python_learning

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(python_learning, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


LOOP_CODE = """total = 0
for number in range(3):
    total = total + number
    print(total)
"""

STATE_WATCH_CODE = """total = 0
for i in range(5):
    total = total + i
    print(total)
if total > 5:
    print("big")
if total > 20:
    print("huge")
"""

FUNCTION_CODE = """def add(a, b):
    total = a + b
    return total

result = add(2, 3)
print(result)
"""

NESTED_FUNCTION_CODE = """def double(x):
    return x * 2

def calculate(n):
    y = double(n)
    return y + 1

print(calculate(4))
"""


def test_python_run_and_step_narration_do_not_duplicate_output(client):
    run = client.post("/python/run", json={"code": LOOP_CODE}).get_json()
    assert run["success"] is True
    assert run["output"].strip() == "0\n1\n3"

    narrated = client.post("/python/step-narration", json={"code": LOOP_CODE}).get_json()
    assert narrated["success"] is True
    prints = [line for line in narrated["narration"] if line.startswith("The program prints")]
    assert prints == ["The program prints 0.", "The program prints 1.", "The program prints 3."]
    assert not any(line.startswith("Output:") for line in narrated["narration"])
    assert len(narrated["narration"]) == len(narrated["indent_depths"])


def test_python_analysis_code_map_and_variable_watch(client):
    analysis = client.post("/python/analyze", json={"code": LOOP_CODE}).get_json()
    assert analysis["success"] is True
    assert "loops" in analysis["analysis"].lower()
    assert "variables" in analysis["analysis"].lower()

    code_map = client.post("/python/audio-code-map", json={"code": LOOP_CODE}).get_json()
    assert code_map["success"] is True
    assert "for loop" in code_map["reply"].lower()
    assert "total" in code_map["reply"]

    watched = client.post(
        "/python/watch-variable",
        json={"code": LOOP_CODE, "action": "add", "variable": "total"},
    ).get_json()
    assert watched["success"] is True
    assert watched["state"]["total"]["value"] == "3"
    assert "total is 3" in watched["speech"].lower()


def test_python_error_recovery_and_mistake_replay(client):
    broken = "for number in range(2):\nprint(number)\n"
    fixed = "for number in range(2):\n    print(number)\n"

    failed = client.post("/python/run", json={"code": broken}).get_json()
    assert failed["success"] is False
    assert "IndentationError" in failed["error"]
    assert "indent" in failed["speech"].lower()

    success = client.post("/python/run", json={"code": fixed}).get_json()
    assert success["success"] is True

    replay = client.post("/python/mistake-replay", json={"code": fixed}).get_json()
    assert replay["success"] is True
    assert "indent" in replay["reply"].lower()
    assert "spaces" in replay["reply"].lower()


def test_python_voice_commands_route_without_breaking_website_commands(client):
    assert client.post("/voice-command", json={"text": "run this code"}).get_json()["action"] == "python_run"
    assert client.post("/voice-command", json={"text": "teach me this code"}).get_json()["action"] == "python_teach"
    assert (
        client.post("/voice-command", json={"text": "audio code map"}).get_json()["action"] == "python_audio_code_map"
    )
    assert (
        client.post("/voice-command", json={"text": "watch variable total"}).get_json()["action"]
        == "python_watch_variable"
    )
    routed = client.post("/voice-command", json={"text": "break when total is greater than 10"}).get_json()
    assert routed["action"] == "python_conditional_breakpoint"
    assert routed["slots"]["condition"] == "total is greater than 10"

    assert client.post("/voice-command", json={"text": "analyze the code"}).get_json()["action"] == "analyze_code"
    assert client.post("/voice-command", json={"text": "run website"}).get_json()["action"] == "run_summary"
    assert (
        client.post("/voice-command", json={"text": "make a website about cats"}).get_json()["action"] == "build_site"
    )


def test_python_input_queue_success_multiple_and_missing(client):
    single = 'name = input("Name: ")\nprint("Hello", name)\n'
    result = client.post("/python/run", json={"code": single, "inputs": ["Amit"]}).get_json()
    assert result["success"] is True
    assert result["output"].strip() == "Name: Amit\nHello Amit"
    assert "Input 1 for prompt 'Name:' used 'Amit'." in result["input_summary"]

    multi = 'first = input("First: ")\nsecond = input("Second: ")\nprint(first + second)\n'
    result = client.post("/python/run", json={"code": multi, "inputs": ["Code", "Up"]}).get_json()
    assert result["success"] is True
    assert result["output"].strip().endswith("CodeUp")
    assert result["inputs_consumed"] == 2

    missing = client.post("/python/run", json={"code": multi, "inputs": ["Only one"]}).get_json()
    assert missing["success"] is False
    assert "input number 2" in missing["error"]
    assert "input queue" in missing["speech"].lower()


def test_python_conditional_audio_breakpoints(client):
    code = "total = 0\nfor i in range(6):\n    total = total + i\n"
    result = client.post(
        "/python/conditional-breakpoint",
        json={"code": code, "condition": "total > 10"},
    ).get_json()
    assert result["success"] is True
    assert result["triggered"] is True
    assert result["line"] == 3
    assert "line 3" in result["speech"].lower()
    assert "total > 10" in result["speech"]
    assert "total" in result["context"]

    spoken = client.post(
        "/python/conditional-breakpoint",
        json={"code": code, "condition": "conditional breakpoint total greater than 10"},
    ).get_json()
    assert spoken["success"] is True
    assert spoken["triggered"] is True

    string_code = 'name = input("Name: ")\nprint("Hello", name)\n'
    string_result = client.post(
        "/python/conditional-breakpoint",
        json={"code": string_code, "condition": 'name == "Amit"', "inputs": ["Amit"]},
    ).get_json()
    assert string_result["success"] is True
    assert string_result["triggered"] is True
    assert "name == 'Amit'" in string_result["condition"]["expression"]

    invalid = client.post(
        "/python/conditional-breakpoint",
        json={"code": code, "condition": '__import__("os")'},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["success"] is False


def test_python_runner_blocks_dangerous_code_and_times_out(client, monkeypatch):
    import codeup.services.python_learning as python_learning

    dangerous_import = client.post("/python/run", json={"code": "import os\nprint(os.listdir('.'))\n"}).get_json()
    assert dangerous_import["success"] is False
    assert "not available" in dangerous_import["speech"].lower()

    dangerous_open = client.post("/python/run", json={"code": "print(open('app.py').read())\n"}).get_json()
    assert dangerous_open["success"] is False
    assert "open" in dangerous_open["speech"].lower()

    monkeypatch.setattr(python_learning, "PYTHON_RUN_TIMEOUT", 1)
    timeout_response = client.post("/python/run", json={"code": "while True:\n    pass\n"})
    timeout = timeout_response.get_json()
    assert timeout["success"] is False
    assert "timed out" in timeout["speech"].lower()

    assert timeout_response.status_code == 200


def test_python_run_status_codes_distinguish_timeout_from_size_limit(client, monkeypatch):
    import codeup.services.python_learning as python_learning

    monkeypatch.setattr(python_learning, "MAX_PYTHON_CODE_SIZE", 10)
    oversized = client.post("/python/run", json={"code": "print('this source is definitely too long')\n"})
    body = oversized.get_json()
    assert body["success"] is False
    assert "too long" in body["error"].lower()
    assert oversized.status_code == 413


def test_python_state_watch_navigation_and_change_explanations(client):
    start = client.post("/python/state-watch", json={"code": STATE_WATCH_CODE, "action": "start"}).get_json()
    assert start["success"] is True
    assert start["cursor"] == 0
    assert start["step"]["line"] == 1
    assert "Step 1" in start["speech"]
    assert "total was set to 0" in start["speech"]

    next_step = client.post("/python/state-watch", json={"code": STATE_WATCH_CODE, "action": "next"}).get_json()
    assert next_step["cursor"] == 1
    assert next_step["step"]["line"] == 2
    assert "loop" in next_step["speech"].lower()

    previous = client.post("/python/state-watch", json={"code": STATE_WATCH_CODE, "action": "previous"}).get_json()
    assert previous["cursor"] == 0
    assert previous["step"]["line"] == 1

    total_change_index = next(
        i for i, step in enumerate(start["steps"]) if step["line"] == 3 and step["changed_variables"]
    )
    changed = client.post(
        "/python/state-watch",
        json={"code": STATE_WATCH_CODE, "action": "what_changed", "cursor": total_change_index},
    ).get_json()
    assert "total changed" in changed["speech"]
    assert " to " in changed["speech"]

    why = client.post(
        "/python/state-watch",
        json={
            "code": STATE_WATCH_CODE,
            "action": "why_variable_change",
            "variable": "total",
            "cursor": total_change_index,
        },
    ).get_json()
    assert "because Python ran line 3" in why["speech"]


def test_python_state_watch_loop_and_condition_explanations(client):
    start = client.post("/python/state-watch", json={"code": STATE_WATCH_CODE, "action": "start"}).get_json()
    fourth_loop_index = next(
        i
        for i, step in enumerate(start["steps"])
        if step["line"] == 3 and step.get("loop_context", {}).get("iteration") == 4
    )
    where = client.post(
        "/python/state-watch",
        json={"code": STATE_WATCH_CODE, "action": "where", "cursor": fourth_loop_index},
    ).get_json()
    assert "4th time through the loop" in where["speech"]
    assert "i is 3" in where["speech"]

    loop = client.post(
        "/python/state-watch",
        json={"code": STATE_WATCH_CODE, "action": "loop", "cursor": fourth_loop_index},
    ).get_json()
    assert "loop on line 2" in loop["speech"]

    pass_index = next(i for i, step in enumerate(start["steps"]) if step["line"] == 5)
    passed = client.post(
        "/python/state-watch",
        json={"code": STATE_WATCH_CODE, "action": "condition_pass", "cursor": pass_index},
    ).get_json()
    assert "total > 5 is true" in passed["speech"]
    assert "total is currently 10" in passed["speech"]

    fail_index = next(i for i, step in enumerate(start["steps"]) if step["line"] == 7)
    failed = client.post(
        "/python/state-watch",
        json={"code": STATE_WATCH_CODE, "action": "condition_fail", "cursor": fail_index},
    ).get_json()
    assert "total > 20 is false" in failed["speech"]
    assert "total is currently 10" in failed["speech"]

    small_false = client.post(
        "/python/state-watch",
        json={"code": 'total = 10\nif total > 20:\n    print("huge")\n', "action": "condition_fail"},
    ).get_json()
    assert "total > 20 is false" in small_false["speech"]
    assert "total is currently 10" in small_false["speech"]


def test_python_state_watch_commands_route_to_python_lane(client):
    examples = [
        ("next step", "next"),
        ("previous step", "previous"),
        ("go back one step", "previous"),
        ("explain this step", "current"),
        ("what changed in Python", "what_changed"),
        ("where am I in Python", "where"),
        ("repeat that", "repeat"),
        ("why did total change", "why_variable_change"),
        ("why did the condition pass", "condition_pass"),
        ("why did the condition fail", "condition_fail"),
        ("explain the loop", "loop"),
    ]
    for command, state_action in examples:
        routed = client.post("/voice-command", json={"text": command}).get_json()
        assert routed["action"] == "python_state_watch"
        assert routed["slots"]["state_action"] == state_action

    assert (
        client.post("/voice-command", json={"text": "make a website about cats"}).get_json()["action"] == "build_site"
    )


def test_python_state_watch_does_not_duplicate_output_in_speech(client):
    start = client.post("/python/state-watch", json={"code": STATE_WATCH_CODE, "action": "start"}).get_json()
    output_lines = [line for line in start["output"].splitlines() if line.strip()]
    assert output_lines == ["0", "1", "3", "6", "10", "big"]
    assert "0\n1\n3" not in start["speech"]

    print_index = next(i for i, step in enumerate(start["steps"]) if step.get("output") == "6")
    current = client.post(
        "/python/state-watch",
        json={"code": STATE_WATCH_CODE, "action": "current", "cursor": print_index},
    ).get_json()
    assert current["speech"].count("The program prints 6.") == 1


def test_python_function_call_watch_simple_call_parameters_and_return(client):
    start = client.post("/python/state-watch", json={"code": FUNCTION_CODE, "action": "start"}).get_json()
    assert start["success"] is True
    assert start["output"].strip() == "5"

    call_index = next(i for i, step in enumerate(start["steps"]) if step.get("function_call"))
    call = start["steps"][call_index]["function_call"]
    assert call["function"] == "add"
    assert call["call_line"] == 5
    assert call["definition_line"] == 1
    assert call["parameters"] == [
        {"name": "a", "value": "2", "argument": "2"},
        {"name": "b", "value": "3", "argument": "3"},
    ]

    step_into = client.post(
        "/python/state-watch",
        json={"code": FUNCTION_CODE, "action": "step_into", "cursor": 0},
    ).get_json()
    assert step_into["cursor"] == call_index
    assert "entering the function add" in step_into["speech"]
    assert "a gets 2" in step_into["speech"]
    assert "b gets 3" in step_into["speech"]

    arguments = client.post(
        "/python/state-watch",
        json={"code": FUNCTION_CODE, "action": "arguments", "cursor": call_index},
    ).get_json()
    assert "call to add passed" in arguments["speech"]
    assert "a gets 2" in arguments["speech"]

    parameters = client.post(
        "/python/state-watch",
        json={"code": FUNCTION_CODE, "action": "parameters", "cursor": call_index},
    ).get_json()
    assert "add has parameters a, b" in parameters["speech"]

    local_index = next(i for i, step in enumerate(start["steps"]) if step["line"] == 2)
    local = client.post(
        "/python/state-watch",
        json={"code": FUNCTION_CODE, "action": "function", "cursor": local_index},
    ).get_json()
    assert "inside add" in local["speech"]
    assert "total is 5" in local["speech"]

    returned = client.post(
        "/python/state-watch",
        json={"code": FUNCTION_CODE, "action": "step_out", "cursor": local_index},
    ).get_json()
    assert returned["step"]["function_return"]["function"] == "add"
    assert returned["step"]["function_return"]["return_value"] == "5"
    assert "returned 5" in returned["speech"]
    assert "line 5" in returned["speech"]
    assert "line 6" in returned["speech"]

    why_returned = client.post(
        "/python/state-watch",
        json={"code": FUNCTION_CODE, "action": "why_function_return", "cursor": local_index},
    ).get_json()
    assert "because Python ran line 3" in why_returned["speech"]
    assert "total is 5" in why_returned["speech"]


def test_python_function_call_watch_nested_calls(client):
    start = client.post("/python/state-watch", json={"code": NESTED_FUNCTION_CODE, "action": "start"}).get_json()
    assert start["success"] is True
    assert start["output"].strip() == "9"

    calculate_index = next(
        i for i, step in enumerate(start["steps"]) if (step.get("function_call") or {}).get("function") == "calculate"
    )
    double_index = next(
        i for i, step in enumerate(start["steps"]) if (step.get("function_call") or {}).get("function") == "double"
    )
    double_call = start["steps"][double_index]["function_call"]
    assert double_call["caller"] == "calculate"
    assert double_call["parameters"][0]["name"] == "x"
    assert double_call["parameters"][0]["value"] == "4"

    into_calculate = client.post(
        "/python/state-watch",
        json={"code": NESTED_FUNCTION_CODE, "action": "step_into", "cursor": 0},
    ).get_json()
    assert into_calculate["cursor"] == calculate_index
    assert "entering the function calculate" in into_calculate["speech"]

    inside_double = client.post(
        "/python/state-watch",
        json={"code": NESTED_FUNCTION_CODE, "action": "function", "cursor": double_index + 1},
    ).get_json()
    assert "inside double" in inside_double["speech"]
    assert "called by calculate" in inside_double["speech"]

    out_of_double = client.post(
        "/python/state-watch",
        json={"code": NESTED_FUNCTION_CODE, "action": "step_out", "cursor": double_index},
    ).get_json()
    assert out_of_double["step"]["function_return"]["function"] == "double"
    assert "returned 8" in out_of_double["speech"]
    assert "line 5" in out_of_double["speech"]

    calculate_return = client.post(
        "/python/state-watch",
        json={"code": NESTED_FUNCTION_CODE, "action": "return", "cursor": out_of_double["cursor"] + 1},
    ).get_json()
    assert calculate_return["step"]["function_return"]["function"] == "calculate"
    assert "returned 9" in calculate_return["speech"]


def test_python_function_call_watch_commands_route_to_python_lane(client):
    examples = [
        ("step into", "step_into"),
        ("step into function", "step_into"),
        ("step out", "step_out"),
        ("leave function", "step_out"),
        ("what function am I in", "where_function"),
        ("what arguments were passed", "arguments"),
        ("what are the parameters", "parameters"),
        ("what did it return", "return"),
        ("where does it go back", "go_back"),
        ("explain this function", "function"),
        ("explain this function call", "function"),
        ("why did this function return this", "why_function_return"),
    ]
    for command, state_action in examples:
        routed = client.post("/voice-command", json={"text": command}).get_json()
        assert routed["action"] == "python_state_watch"
        assert routed["slots"]["state_action"] == state_action

    assert (
        client.post("/voice-command", json={"text": "make a website about cats"}).get_json()["action"] == "build_site"
    )


def test_python_function_call_watch_does_not_duplicate_output_in_speech(client):
    start = client.post("/python/state-watch", json={"code": FUNCTION_CODE, "action": "start"}).get_json()
    assert start["output"].strip() == "5"
    assert "\n5\n" not in start["speech"]

    returned = client.post(
        "/python/state-watch",
        json={"code": FUNCTION_CODE, "action": "return"},
    ).get_json()
    assert returned["speech"].count("returned 5") == 1


def test_frontend_exposes_accessible_python_lab():
    html = open("templates/index.html", encoding="utf-8").read()
    script = open("static/codeup-html.js", encoding="utf-8").read()

    assert 'id="tabPython"' in html
    assert 'aria-controls="panelPython"' in html
    assert 'aria-label="Python editor"' in html
    assert 'id="runPythonBtn"' in html
    assert 'id="pythonInputValue"' in html
    assert 'id="pythonBreakpointInput"' in html
    assert 'id="pythonNextStepBtn"' in html
    assert 'id="pythonExplainConditionBtn"' in html
    assert 'id="pythonStepIntoBtn"' in html
    assert 'id="pythonFunctionReturnBtn"' in html
    assert 'id="pythonHistoryList"' in html
    assert "function runPythonCode(" in script
    assert "function runPythonWithInputs(" in script
    assert "function pythonConditionalBreakpoint(" in script
    assert "function pythonStateWatch(" in script
    assert "pythonStepNarration" in script
    assert "pythonWatchVariable" in script
    assert "showPythonHistory" in script
    assert "getPython()" in script
