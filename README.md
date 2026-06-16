# CodeUp Web

*A voice-first accessible website builder for beginners.*

[![CI](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml/badge.svg)](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml)

Build a website by describing it. Ask CodeUp Web to explain the structure. Check
accessibility, then export your project with notes you can study later — all by
voice or by typing.

## What is CodeUp Web?

CodeUp Web helps beginners, especially blind and visually impaired learners,
create accessible websites and small web apps through typed or spoken
natural-language commands. You describe what you want, CodeUp Web generates a
complete `index.html`, `style.css`, and `script.js`, previews it, and explains it
in plain language. You can then improve it with natural edits, check
accessibility, fix safe issues, and download a ZIP.

It is a sister project to **CodeUp**, the voice-first Python learning environment.
CodeUp teaches beginner Python through voice-first coding; CodeUp Web applies the
same accessibility-first idea to website creation and web-code understanding.

## Why this exists

Website builders usually focus on what a page *looks* like. Code editors usually
assume the learner can inspect layout visually. Neither is friendly to someone who
works mainly by ear.

CodeUp Web tries to make website creation understandable without sight: through
speech, clear structure, plain-language explanations, code maps, step narration,
accessibility checks, screen-reader summaries, and exportable learning notes. The
typed command box mirrors every spoken command, so nothing depends on a working
microphone.

## ✨ Core features

- Natural-language website generation
- Multiple project types (see below)
- Accessible HTML / CSS / JavaScript generation
- Natural editing of generated websites ("add an about section", "make it simpler")
- Code map / website map
- Step narration of how the project loads and runs
- File explanations for `index.html`, `style.css`, and `script.js`
- Preview description (a sighted-guide style summary of the page)
- Page landmarks listing
- Accessibility audit with severity, why it matters, and suggested fixes
- Accessibility fix suggestions and safe deterministic autofixes
- Learning notes, project review, and project summary
- Memory bookmarks, change replay, trainer notes, and a student recap
- Screen-reader / NVDA preparation summary
- A short guided beginner tutorial
- ZIP export with code and learning artifacts
- Typed command fallback for every voice command
- Voice-first design with speech output where the browser supports it
- Deterministic fallback templates when cloud AI is unavailable
- Gentle command repair for common typos (e.g. "check accessiblity" → "check accessibility")

## 🗂️ Supported project types

CodeUp Web routes a request to an allowlisted project type and builds a matching,
accessible template:

- portfolio
- school club
- robotics club
- project showcase
- event / workshop
- bakery / small business
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

## 💬 Example commands

Every command works whether spoken or typed — both go through the same parser.

**Create**

- `make a website for my school robotics club`
- `make a portfolio website`
- `make a quiz app about Python basics`
- `make a bakery website`
- `make a calculator app`

**Edit**

- `add an about section`
- `make it more professional`
- `change the title`
- `add a contact form`
- `make it simpler`
- `add score tracking`

**Understand**

- `code map`
- `step narration`
- `landmarks`
- `explain JavaScript`
- `explain CSS`
- `describe preview`
- `learning notes`
- `review project`

**Accessibility**

- `check accessibility`
- `fix accessibility issues`
- `accessibility map`
- `prepare this for NVDA`

**Learn, teach, and revisit**

- `start tutorial` (then `next`, `repeat`, `exit tutorial`)
- `make trainer notes`
- `what did I learn today`
- `bookmark the contact form as contact area`
- `list bookmarks`
- `replay change`
- `what changed`

**Export**

- `export website`

**Control**

- `what can I do here`
- `start over`
- `stop everything`

## ▶️ Demo flow

Start the server, open `http://127.0.0.1:5000/ide`, click the command box, and run
these in order. If the microphone is unavailable, keep typing — the routing is
identical.

**Short 5-minute demo**

1. `what can I do here`
2. `make a website for my school robotics club`
3. `code map`
4. `step narration`
5. `add a section about competitions`
6. `check accessibility`
7. `fix accessibility issues`
8. `learning notes`
9. `export website`

**Optional app demo**

1. `start over`
2. `make a quiz app about Python basics`
3. `add score tracking`
4. `explain JavaScript`
5. `describe preview`
6. `export website`

Say or type `stop everything` (or press **Stop Speaking**) at any point to cancel
speech, listening, and stale background work instantly.

## 📦 How export works

`export website` downloads a ZIP. It always includes the source files, a
`README.txt`, a `manifest.json`, and a set of plain-text learning artifacts
generated from the current project:

- `index.html`
- `style.css`
- `script.js` (when the project uses JavaScript)
- `README.txt`
- `CODE_MAP.txt`
- `STEP_NARRATION.txt`
- `LEARNING_NOTES.txt`
- `PROJECT_SUMMARY.txt`
- `PROJECT_REVIEW.txt`
- `PREVIEW_DESCRIPTION.txt`
- `TRAINER_NOTES.txt`
- `STUDENT_RECAP.txt`
- `SCREEN_READER_SUMMARY.txt`
- `ACCESSIBILITY_REPORT.txt` (when an audit has run)
- `CHANGE_REPLAY.txt` (when you edited the project)
- `BOOKMARKS.txt` (when you saved bookmarks)

Artifacts are generated at export time from the current project and session state,
so export never fails just because you skipped a step earlier.

## ♿ Accessibility-first design

CodeUp Web is built for non-visual use first:

- semantic HTML landmarks (header, navigation, main, sections, footer)
- a clear heading outline
- labels for form controls
- readable button and link text
- visible keyboard focus
- non-visual preview descriptions and screen-reader summaries
- screen-reader-oriented structure (landmarks, reading order, heading levels)
- a typed command fallback for every voice command
- speech output where the browser supports it
- Chrome or Edge recommended for the browser speech APIs

The interface also includes color-vision modes, a dyslexia-friendly mode, reduce
motion, night mode, and a calmer Demo Mode for classroom projectors.

## 🔒 Safety

Generated projects are meant to be safe starter websites. CodeUp Web avoids and
validates against:

- unsafe JavaScript and inline event handlers
- `eval`-based calculators
- credential harvesting or fake login flows
- phishing pages
- remote tracking scripts
- hidden or silent data submission

Generated and edited files are validated before they load, and student previews
are served under a restrictive Content Security Policy. This README only
summarizes safety; the full security policy, hosted-preview restrictions, and how
to report a vulnerability live in [SECURITY.md](SECURITY.md).

## 🚀 Running locally

Requirements: Python 3.10 or newer. Chrome or Edge is recommended for voice.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py app.py
```

Then open:

```text
http://127.0.0.1:5000/ide
```

**No-key demo mode.** CodeUp Web works without any cloud AI key. For a fully
deterministic, offline-style demo:

```powershell
$env:AI_CLOUD_ENABLED="0"
py app.py
```

In this mode CodeUp Web still generates complete accessible projects, previews
them, explains them, audits and fixes accessibility, and exports the ZIP.

### AI configuration (optional)

With a provider key, generation and explanations are more varied. Keys are
server-side environment variables only; the browser never accepts provider keys.

```text
XAI_API_KEY=your_xai_key        # or GROK_API_KEY
XAI_MODEL=grok-3-mini
GROQ_API_KEY=your_groq_key       # Groq is also supported
GROQ_MODEL=llama-3.3-70b-versatile
AI_CLOUD_ENABLED=0               # disable cloud AI for offline demos
```

The older `GEMINI_ENABLED=0` flag still works as a compatibility alias.

## 🧪 Testing

Install dev dependencies first: `pip install -r requirements-dev.txt`.

```powershell
py -m pytest -q
py -m compileall -q .
py -m ruff check codeup app.py tests
py -m ruff format --check codeup app.py tests
node --check static/codeup-html.js
node --check static/voice-memory-engine.js
```

The Python suite covers routing, project-type classification, generation safety,
project explanations, accessibility audits and autofixes, ZIP export, storage,
session security, the voice-engine state machine, and a full-file JavaScript
harness run under Node's `vm`. An optional browser end-to-end suite uses
Playwright (`tests/test_e2e_browser.py`) and is skipped when no browser is
available.

## 🏗️ Architecture

```text
CodeUp-web/
├── app.py                    # Entry point (thin wrapper)
├── codeup/
│   ├── app_factory.py        # Flask app factory (create_app)
│   ├── config.py             # Environment config and constants
│   ├── security.py           # CSRF/origin checks, CSP headers, HTML sanitization
│   ├── storage.py            # Storage abstraction (JSON file backend)
│   ├── models.py             # Typed domain models
│   ├── routes/               # Flask blueprints (core, site, ai, learning, ...)
│   └── services/             # Generation, editing, audit, explainers, routing
├── static/
│   ├── codeup-html.js        # Frontend IDE controller (editors, commands, preview)
│   ├── voice-memory-engine.js# Voice state machine and streaming
│   └── style/                # CSS modules (core, accessibility, ui-improvements, ide)
├── templates/index.html      # Single-page app shell
└── tests/                    # Python + Node-harness test suite
```

The backend uses the app-factory pattern with blueprints organized by domain.
Command routing is rule-based and deterministic in `services/intent_router.py`;
explanations and learning artifacts are produced in `services/project_explainer.py`
and `services/web_learning.py`. Runtime data lives under `instance/data` (or
`DATA_DIR`) and is ignored by Git.

Sessions are temporary interaction state; named **projects** persist pages, audit
history, and restorable versions. Build, edit, audit-fix, and polish actions each
create a version that can be restored.

## ⚠️ Known limitations

- Real microphone and text-to-speech depend on browser support; Chrome or Edge is
  recommended (Firefox and Safari do not support the Web Speech API used here).
- AI features depend on configured keys and server settings; without a key, the
  deterministic templates are used.
- Generated websites are beginner projects, not production SaaS apps.
- No-cloud mode uses fixed template structures; a cloud key produces more variety.
- Multi-page and framework projects are out of scope unless added later.
- Screen-reader focus order is derived from deterministic HTML analysis; exact
  NVDA, JAWS, or VoiceOver behavior is a pending hardware test.

## 🤝 Relationship to CodeUp

CodeUp teaches beginner Python through a voice-first, accessibility-first coding
experience. CodeUp Web is its sister project: it brings the same idea to the web,
so a learner can build a website, understand its HTML/CSS/JavaScript, check its
accessibility, and export it — using speech or the typed command box. The two
projects share a philosophy, not a codebase; CodeUp Web is not part of the main
CodeUp Python IDE.

## Contributing

1. Fork the repo and create a feature branch.
2. Install dev dependencies: `pip install -r requirements-dev.txt`.
3. Run `ruff check`, `ruff format --check`, `pytest`, and the `node --check`
   commands above before opening a PR.
4. CI runs lint, format checks, Python tests, and JS syntax validation on every
   push and PR to `main`.

---

*Note: AI assistance was used for portions of the codebase restructuring and
reorganization. The project's main writing, framing, and initial direction were
authored by the maintainer.*
