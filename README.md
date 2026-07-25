# CodeUp Web

[![CI](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml/badge.svg)](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml)

CodeUp Web is an accessibility-first learning IDE for beginners who want to build and understand small websites and web apps. It accepts spoken or typed commands, generates editable HTML, CSS, and JavaScript projects, previews them locally, explains the code, audits accessibility, applies safe accessibility fixes, and exports the finished starter project. The local Python workflow runs the Flask app and test suite without requiring cloud AI.

## Run Locally

Requirements: Python 3.10 or newer. Chrome or Edge is recommended for speech features.

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

Use the command box or microphone to create and revise a web project:

```text
make a website for my school robotics club
code map
step narration
check accessibility
fix accessibility issues
export website
```

The IDE keeps separate HTML, CSS, and JavaScript editors with a live preview. Generated projects include an `index.html`, `style.css`, `script.js`, and an export `README.txt`, plus learning reports such as code maps, accessibility reports, step narration, project review, and preview description when those reports are available.

## Safety

Generated websites are starter projects, not production applications. CodeUp Web blocks unsafe JavaScript patterns, external tracking scripts, credential harvesting, fake login flows, silent form submission, and remote student-site script loading where the local validator can detect them.

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
