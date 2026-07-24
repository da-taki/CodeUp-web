# CodeUp Web

A voice-first, accessibility-focused website builder for beginners.

[![CI](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml/badge.svg)](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml)

CodeUp Web helps a beginner describe a website or small web app, edit the generated HTML, CSS, and JavaScript, preview it locally, ask for plain-language explanations, check accessibility, and export a ZIP with study notes. It is designed for typed commands and spoken commands, with a focus on blind and visually impaired learners who need more than a visual canvas.

## What Reviewers Should Know

CodeUp Web is a standalone Flask app. It is related to the broader CodeUp idea, but this repository is the web-builder implementation: the Flask routes, deterministic project generator, local Monaco editor integration, browser IDE, accessibility checks, project storage, export pipeline, Python learning lane, and test suite live here.

The strongest completed pieces are:

- A single-page IDE with HTML, CSS, JavaScript, and Python editor panes.
- Local Monaco editor loading with a textarea fallback when Monaco is unavailable.
- Deterministic offline website and app generation, so demos work without cloud AI keys.
- Website preview publishing under `/student-site/<session>/...` with restrictive preview CSP headers.
- Project creation, loading, autosave, version history, undo, and ZIP export.
- Accessibility audit, safe autofixes, screen-reader summaries, keyboard checks, readiness reports, and learner notes.
- Runtime and debugging teachers that inspect HTML/CSS/JS connections without inventing browser behavior.
- Python run, input, step narration, audio code maps, variable watches, function watches, and conditional breakpoints.

## Problem And Users

Many beginner website tools assume the learner can inspect a page visually. CodeUp Web tries to make the structure and behavior of a site understandable by ear and by keyboard. The intended users are beginners, teachers, workshop facilitators, and blind or low-vision learners who need accessible explanations, predictable controls, and exportable learning artifacts.

## Core Features

- Natural-language website generation and editing.
- Typed command fallback for every voice-oriented workflow.
- HTML, CSS, JavaScript, and Python editing in one workspace.
- Live preview with desktop, tablet, and mobile viewport controls.
- Project save/load, autosave, local persistence, version history, and undo.
- Design remix with undo support.
- Accessibility audit with severity, explanations, and deterministic safe fixes.
- Runtime teacher, debug teacher, selector explainer, screen-reader tour, keyboard test, and readiness score.
- Guided web tutorials and guided project starters.
- Python execution with input queues, step narration, code maps, variable/function watches, and conditional breakpoints.
- ZIP export containing source files plus learning and audit artifacts.

## Supported Project Types

The generator routes requests to an allowlisted project type and produces a beginner-safe starter:

- portfolio
- school club
- robotics club
- project showcase
- event or workshop
- bakery or small business
- nonprofit
- accessibility project
- blog
- gallery
- product page
- quiz app
- calculator app
- to-do list app
- flashcard app
- poll page
- contact form
- dashboard
- timetable
- habit tracker
- resume
- generic website

These are starter projects, not complete production apps or full courses.

## Local Setup

Requirements: Python 3.10 or newer. Node/npm is recommended for verifying or refreshing the pinned Monaco package, and Chrome or Edge gives the best speech and browser-test support.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
# Optional: verifies package metadata for the vendored Monaco editor.
npm install
py app.py
```

Then open:

```text
http://127.0.0.1:5000/
```

The `/ide` route loads the same app shell and is safe to open directly.

## Environment Variables

CodeUp Web works without cloud AI keys. For deterministic local demos, run with cloud AI disabled:

```powershell
$env:AI_CLOUD_ENABLED="0"
py app.py
```

Supported environment variables are documented in `.env.example`:

```text
FLASK_SECRET_KEY=change-me-in-production
CODEUP_ENV=development
SESSION_COOKIE_SECURE=false
XAI_API_KEY=your_xai_or_grok_key_here
GROK_API_KEY=your_xai_or_grok_key_here
GROQ_API_KEY=your_groq_api_key_here
AI_CLOUD_ENABLED=1
AI_MAX_CONCURRENT=3
AI_TIMEOUT=30
SESSION_ARTIFACT_MAX_AGE=604800
DATA_DIR=instance/data
ALLOWED_ORIGINS=
```

Do not commit a real `.env` file or provider key.

## Demo flow

Use the command box if microphone support is unavailable. The same router handles typed and spoken commands.

1. `what can I do here`
2. `make a website for my school robotics club`
3. `code map`
4. `step narration`
5. `add a section about competitions`
6. `check accessibility`
7. `fix accessibility issues`
8. `learning notes`
9. `export website`

Optional app demo:

1. `start over`
2. `make a quiz app about Python basics`
3. `add score tracking`
4. `explain JavaScript`
5. `describe preview`
6. `export website`

Proof-oriented demo:

1. `make a website for my school robotics club`
2. `run website`
3. `what CSS affects the join button`
4. `debug website`
5. `check accessibility`
6. `is this ready to share`
7. `what changed`
8. `make pilot report`
9. `export website`

## Export Contents

`export website` downloads a ZIP. It always includes source files and core learning artifacts, and includes conditional reports when the current session has enough data.

- `index.html`
- `style.css`
- `script.js`
- `README.txt`
- `manifest.json`
- `CODE_MAP.txt`
- `STEP_NARRATION.txt`
- `LEARNING_NOTES.txt`
- `PROJECT_SUMMARY.txt`
- `PROJECT_REVIEW.txt`
- `PREVIEW_DESCRIPTION.txt`
- `TRAINER_NOTES.txt`
- `STUDENT_RECAP.txt`
- `SCREEN_READER_SUMMARY.txt`
- `RUN_SUMMARY.txt`
- `DEBUG_REPORT.txt`
- `SCREEN_READER_TOUR.txt`
- `KEYBOARD_TEST.txt`
- `VISUAL_DESCRIPTION.txt`
- `READINESS_SCORE.txt`
- `TEACHER_REVIEW.txt`
- `ACCESSIBILITY_REPORT.txt` when an audit has run
- `PILOT_REPORT.txt` when session data exists
- `VERSION_HISTORY.txt` when versions exist
- `CHANGE_REPLAY.txt` when an edit has been recorded
- `BOOKMARKS.txt` when bookmarks exist

## Testing

```powershell
py -m pytest -q
py -m ruff check .
py -m ruff format --check codeup app.py tests
py -m compileall -q app.py codeup tests
node --check static/codeup-html.js
node --check static/monaco-loader.js
node --check static/voice-memory-engine.js
```

The browser end-to-end tests are in `tests/test_e2e_browser.py`. They use Playwright and skip only when no Chromium-compatible browser is available.

## Build And Assets

There is no separate frontend build step. Static files are served directly by Flask. Monaco is pinned in `package-lock.json` and vendored under `static/vendor/monaco/vs` so the editor loads from same-origin files instead of a CDN.

If Monaco needs to be refreshed, run `npm install` and update the vendored files through the repository's normal asset process. Do not hand-edit generated vendor bundles.

## Architecture

```text
CodeUp-web/
|-- app.py                    Flask entry point
|-- codeup/
|   |-- app_factory.py        Flask app factory
|   |-- config.py             Environment and app constants
|   |-- security.py           CSP, origin checks, and HTML sanitization
|   |-- storage.py            JSON-backed local storage
|   |-- models.py             Domain models
|   |-- routes/               Flask blueprints
|   |-- runtime/              Python runner sandbox
|   `-- services/             Generation, routing, audit, explainers, export
|-- static/
|   |-- codeup-html.js        Browser IDE controller
|   |-- monaco-loader.js      Local Monaco bootstrap
|   |-- voice-memory-engine.js
|   `-- style/                CSS modules
|-- templates/index.html      Single-page app shell
|-- tests/                    Python and browser tests
`-- docs/evidence/            Existing screenshots for verification evidence
```

Runtime data is stored under `instance/data` by default or under `DATA_DIR` when configured. Local data directories and `.env` are ignored by Git.

## Safety

Generated projects are starter sites for learning. CodeUp Web validates generated and edited files, strips external scripts and styles from hosted previews, avoids credential-harvesting templates, and serves student previews with restrictive security headers. See [SECURITY.md](SECURITY.md) for the full policy.

## Known Limitations

- Voice input and speech output depend on browser support; Chrome or Edge is recommended.
- Without cloud AI keys, generation uses deterministic templates with limited variation.
- Guided projects are starter flows and are not full milestone-validated courses.
- Generated websites are beginner projects, not production services.
- Framework projects and arbitrary multi-page application architectures are outside the current scope.
- Screen-reader behavior is tested through deterministic structure checks; exact NVDA, JAWS, and VoiceOver hardware testing remains a manual validation step.

## Contributing

1. Install runtime and dev dependencies.
2. Run the tests and checks listed above.
3. Keep README and UI claims specific to behavior that is implemented and tested.
4. Do not commit secrets, local `.env` files, runtime data, caches, or generated test artifacts.
