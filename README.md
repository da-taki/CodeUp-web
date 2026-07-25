# CodeUp Web

A voice-first learning IDE for building websites and exploring beginner Python.

CodeUp Web lets beginners create, edit, understand, test, and export websites through typed or spoken commands. It also includes a Python learning workspace with audio code maps, step narration, state tracking, function explanations, and conditional breakpoints.

I built it for learners who need more than a visual canvas. The interface works with keyboard navigation, screen readers, spoken feedback, and plain-language explanations.

## What You Can Build

Describe a project in everyday language and CodeUp Web generates an editable HTML, CSS, and JavaScript starter.

Examples include:

- portfolios and resumes
- school clubs and events
- project showcases
- small business pages
- quizzes and calculators
- to-do lists and habit trackers
- blogs, galleries, and dashboards

The generated projects are learning starters. Every file remains visible and editable.

## Website Workspace

The website workspace includes:

- HTML, CSS, and JavaScript editors
- locally hosted Monaco Editor
- textarea fallback when Monaco is unavailable
- live desktop, tablet, and mobile previews
- typed and spoken commands
- deterministic offline generation
- natural-language editing
- autosave and project loading
- version history and undo
- design remix with undo
- ZIP export

CodeUp Web can explain the structure and behavior of a project through:

- audio code maps
- step narration
- runtime summaries
- HTML, CSS, and JavaScript explanations
- selector tracing
- change replay
- project reviews
- learning notes

## Python Learning Workspace

Python mode supports beginner programs using variables, conditions, loops, functions, collections, and queued input values.

Learning tools include:

- constrained Python execution
- plain-language error explanations
- audio code maps
- indentation and nesting descriptions
- step-by-step narration
- variable state watches
- function call and return explanations
- conditional breakpoints
- output and execution limits

Python programs run in a separate constrained process with a timeout and a restricted import surface. This environment is intended for beginner learning programs.

## Accessibility Tools

CodeUp Web includes deterministic checks and explanations for:

- missing accessible names
- heading and landmark structure
- image alternative text
- keyboard navigation
- focus visibility
- form labels
- screen-reader reading order
- color and contrast concerns
- common HTML accessibility problems

The accessibility audit can apply a limited set of safe fixes. Reports explain what changed and why.

Automated checks support learning and review. Exact behavior with NVDA, JAWS, and VoiceOver still requires manual testing.

## Guided Learning

The app includes short web tutorials and guided project starters.

Tutorial progress is saved between reloads. Guided projects provide a structured starting path while leaving the learner in control of the code.

These flows are project starters rather than full courses.

## Quick Start

### Requirements

- Python 3.10 or newer
- Chrome or Edge recommended for speech features
- Node.js is optional because Monaco is already vendored in the repository

### Install

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
source .venv/bin/activate
```

Install dependencies and start the app:

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

The IDE can also be opened directly at:

```text
http://127.0.0.1:5000/ide
```

## Cloud AI Is Optional

CodeUp Web works without provider keys. Deterministic generation and analysis remain available offline.

To force deterministic local behavior:

Windows PowerShell:

```powershell
$env:AI_CLOUD_ENABLED="0"
python app.py
```

macOS or Linux:

```bash
AI_CLOUD_ENABLED=0 python app.py
```

Optional provider settings and other configuration values are documented in `.env.example`.

Never commit a real `.env` file or API key.

## Demo Flow

### Build a Website

Try these commands in the command box:

```text
make a website for my school robotics club
code map
add a section about competitions
check accessibility
fix accessibility issues
what changed
export website
```

### Explore Python

Open the Python workspace and try:

```python
total = 0

for score in [8, 12, 15]:
    total += score

print(total)
```

Then use:

```text
run this Python code
audio code map
next step
watch variable total
why did total change
break when total > 10
```

## Export

Website export produces a ZIP containing the editable source files and the learning reports available for the current project.

Depending on the actions completed during the session, the export may include:

- code maps
- step narration
- accessibility findings
- runtime and debugging reports
- project summaries
- learning notes
- version history
- change replay
- teacher and student recaps

## Testing

Run the complete test suite:

```bash
python -m pytest -q
```

Run the checks separately:

```bash
python -m ruff check .
python -m ruff format --check codeup app.py tests
python -m compileall -q app.py codeup tests
node --check static/codeup-html.js
node --check static/monaco-loader.js
node --check static/voice-memory-engine.js
```

Run the browser tests:

```bash
python -m pytest tests/test_e2e_browser.py -q
```

The current verified suite contains:

- 441 non-browser tests
- 16 browser end-to-end tests
- Python 3.10 and Python 3.12 CI coverage

## Tech Stack

- Python and Flask
- Vanilla JavaScript
- HTML and CSS
- Monaco Editor 0.56.0
- Python AST analysis
- browser speech synthesis and recognition
- Playwright browser testing
- JSON-backed local project storage

Monaco is served from `static/vendor/monaco/` so the editor can load from the same origin without a CDN.

## Project Structure

```text
CodeUp-web/
├── app.py
├── codeup/
│   ├── app_factory.py
│   ├── config.py
│   ├── routes/
│   ├── runtime/
│   ├── services/
│   ├── security.py
│   └── storage.py
├── static/
│   ├── codeup-html.js
│   ├── monaco-loader.js
│   ├── voice-memory-engine.js
│   ├── style/
│   └── vendor/monaco/
├── templates/
├── tests/
└── docs/evidence/
```

## Safety and Limits

- Hosted previews remove external scripts and remote stylesheets.
- Student previews use restrictive Content Security Policy headers.
- Generated projects avoid credential-harvesting and hidden submission flows.
- Python mode restricts imports, reflective access, output size, execution time, and input size.
- Python mode is a constrained educational runner and should not be used as a security boundary for hostile untrusted code.
- Voice input and speech output depend on browser support.
- Offline generation has less variation than cloud-assisted generation.
- Generated projects are beginner starters rather than production applications.
- Framework projects and arbitrary application architectures are outside the current scope.

See [SECURITY.md](SECURITY.md) for the security policy and vulnerability-reporting process.

## Evidence

Additional browser evidence is available in `docs/evidence`, including:

- Monaco and fallback editors
- desktop and mobile layouts
- website preview
- Python learning mode
- guided projects
- version history
- ZIP export
- keyboard focus
