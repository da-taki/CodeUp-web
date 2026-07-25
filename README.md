# CodeUp Web

[![CI](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml/badge.svg)](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml)

CodeUp Web is an accessibility-first learning IDE for beginners who want to build websites and explore starter Python programs. It accepts typed or spoken commands, keeps code editable, explains what changed, and works without cloud AI for deterministic classroom demos.

## Run Locally

Requirements: Python 3.10 or newer and Node.js for JavaScript syntax checks. Chrome or Edge is recommended for speech and Monaco editor testing.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FLASK_TESTING="true"
$env:GEMINI_ENABLED="0"
$env:AI_CLOUD_ENABLED="0"
py app.py
```

Open:

```text
http://127.0.0.1:5000/
http://127.0.0.1:5000/ide
```

## Website Workflow

Create and revise a web project from the command box or microphone:

```text
make a website for my school robotics club
code map
step narration
check accessibility
fix accessibility issues
export website
```

The website workspace includes HTML, CSS, and JavaScript editors, Monaco with a textarea fallback, live preview, save and reload, version history, undo, accessibility audits, safe accessibility fixes, guided projects, and ZIP export. Exports include `index.html`, `style.css`, `script.js`, `README.txt`, and learning reports generated from the current project state.

## Python Workflow

Use the Python workspace for beginner programs with input, output, variable state, functions, loops, and errors:

```text
print("Hello, CodeUp")
```

Python execution runs in a constrained process with timeout handling, limited imports, queued input, plain-language error explanations, audio code maps, step narration, state watches, and conditional breakpoints.

## Safety

Generated websites and Python runs are learning starters, not production applications. CodeUp Web blocks unsafe website patterns such as remote scripts, hidden data submission, credential harvesting, fake login flows, and unsafe JavaScript where the local validators can detect them. Python execution is bounded and intentionally limited for beginner practice.

The full policy and vulnerability reporting details are in [SECURITY.md](SECURITY.md).

## Tests

Use these checks before submitting changes:

```powershell
py -m ruff check .
py -m ruff format --check codeup app.py tests
py -m compileall -q app.py codeup tests
node --check static/codeup-html.js
node --check static/monaco-loader.js
node --check static/voice-memory-engine.js
py -m pytest tests --ignore=tests/test_e2e_browser.py -q
py -m pytest tests/test_e2e_browser.py -q
git diff --check
```

Use these environment values for deterministic local checks:

```text
FLASK_TESTING=true
GEMINI_ENABLED=0
AI_CLOUD_ENABLED=0
```
