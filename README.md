# CodeUp HTML

[![CI](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml/badge.svg)](https://github.com/da-taki/CodeUp-web/actions/workflows/ci.yml)

CodeUp HTML is a blind-first website builder for students who want to create
real HTML websites through conversation, keyboard, and voice. This sister
project is focused only on websites: build pages, save named projects, preview
locally, hear a visual review, apply improvements, audit accessibility, and
export either a single HTML file or a multi-page ZIP.

## Demo Flow

Start the server:

```text
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

Try this full review loop:

```text
Hello, what all can I do in here?
Build a website for my robotics club
Preview website
What do you think is missing here?
Add that
Review website
Audit website
Export website
```

The important loop is:

1. Student asks CodeUp HTML to build a website.
2. The app writes HTML and hosts it at `/student-site/<session-id>/`.
   Hosted session sites intentionally serve generated `.html` pages only; CSS,
   JavaScript, and media should stay inline in those pages.
3. CodeUp gives a sighted-guide style review for blind students: what the page
   looks like, what is missing, and what to add next.
4. Student says `add that` or `fix missing things`.
5. CodeUp edits the HTML, republishes the local site, and reviews the new
   version.

## No-Key Demo Mode

CodeUp HTML works even when no cloud AI key is configured. For a deterministic
pilot demo, run:

```text
AI_CLOUD_ENABLED=0 python app.py
```

On Windows PowerShell:

```text
$env:AI_CLOUD_ENABLED="0"
python app.py
```

In this mode, CodeUp still:

- answers what the tool can do,
- builds a complete accessible HTML website,
- hosts the preview locally,
- gives a blind-first visual review,
- applies the latest review suggestions,
- explains the current site,
- audits accessibility,
- outlines the page structure,
- polishes/wraps HTML,
- exports the website as an `.html` file or project ZIP.

## Student Features

- Conversational guide for questions like `what can I do here?`
- Natural-language website generation from `Build a website for ...`
- Named project save/load, duplication, autosave, and server-side versions
- Local preview at `/student-site/<session-id>/`
- Sighted-guide review loop for `what is missing?` and `add that`
- Guided audit fixes with before/after version snapshots
- Audio explanation of what the site looks like
- Hindi/Hinglish and English voice workflows
- `pause voice`, `resume voice`, and `stop speaking`
- Speech cancellation when a new command starts
- HTML sonification with different tones for page structure
- Accessibility audit with a score and fix list
- Page outline from headings
- One-click single-page HTML export and multi-page ZIP export
- Demo Mode for larger, calmer classroom presentation
- Reset session for the next student
- Per-session memory for recent prompts, current HTML, preview URL, and latest
  visual review

## Architecture

```
CodeUp-web/
├── app.py                  # Entry point (thin wrapper)
├── codeup/                 # Backend package
│   ├── app_factory.py      # Flask app factory (create_app)
│   ├── config.py           # Environment config and constants
│   ├── logging.py          # Structured logging with request/session IDs
│   ├── models.py           # Typed domain models (HtmlMemory, AuditResult)
│   ├── security.py         # CSRF, CSP headers, HTML sanitization
│   ├── storage.py          # Storage abstraction (JSON file backend)
│   ├── routes/             # Flask blueprints
│   │   ├── core.py         # Home, healthz, voice-command
│   │   ├── site.py         # Publish, preview, audit, autofix, export, reset
│   │   ├── ai_routes.py    # Generate, chat, review, explain, fix, stream
│   │   ├── memory.py       # HTML memory, smart memory, build context
│   │   └── projects.py     # Named projects and persisted versions
│   └── services/           # Business logic
│       ├── ai_service.py   # AI provider integration (xAI, Groq, Ollama)
│       ├── fallbacks.py    # Offline fallback responses
│       ├── html_utils.py   # HTML parsing, audit, accessibility checks
│       └── memory_service.py  # Smart memory deduplication and context
├── static/
│   ├── codeup-html.js      # Main frontend application
│   ├── voice-memory-engine.js  # Voice state machine and streaming
│   └── style/              # CSS modules
├── templates/
│   └── index.html          # Single-page app template
├── tests/                  # Test suite (100+ tests)
├── .github/workflows/ci.yml  # GitHub Actions CI
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Dev dependencies (includes linting)
└── pyproject.toml          # Ruff linter and pytest config
```

The backend uses the **app factory pattern** (`create_app`) with Flask
blueprints. Routes are organized by domain (core, site, AI, memory).
Business logic lives in service modules. The storage layer abstracts file
I/O so the backing store can be swapped without changing route handlers.

Session artifacts (memory JSON files and hosted student sites) are cleaned
up automatically based on `SESSION_ARTIFACT_MAX_AGE` (default: 7 days).

Runtime data lives under `instance/data` by default, or under `DATA_DIR` when
configured. The data directory is organized into `projects/`, `html_memory/`,
`student_sites/`, `exports/`, and `tmp/`; these paths are runtime artifacts and
are ignored by Git. Older repo-root `html_memory/` files are read and copied
into the configured data directory when first accessed.

## Projects And Versions

CodeUp HTML now separates temporary session state from named projects. A session
still owns the current browser interaction and hosted preview, while a project
is a persisted entity with a name, page set, audit history, and version list.

Project routes:

```text
GET  /projects
POST /projects
GET  /projects/<project_id>
PATCH /projects/<project_id>
POST /projects/<project_id>/autosave
POST /projects/<project_id>/duplicate
GET  /projects/<project_id>/versions
POST /projects/<project_id>/versions
POST /projects/<project_id>/versions/<version_id>/restore
```

Automated edits return deterministic change summaries and store those summaries
in version metadata when a project is active.

## Voice Engine

The voice system uses a strict state machine with validated transitions:

```
IDLE -> LISTENING -> PROCESSING -> RESPONDING -> SPEAKING -> LISTENING
```

Interrupt from any active state jumps back to LISTENING instantly.

### Real-Time Streaming

AI responses stream live from the server via SSE. Text appears in the UI
immediately as chunks arrive (throttled at ~35ms). Narration begins early using
micro-chunk extraction (~22 character word-boundary phrases) instead of waiting
for full sentences.

### Instant Interrupt (Barge-In)

When the user starts speaking during a response:

1. `speechSynthesis.cancel()` fires immediately
2. The active AI fetch is aborted via `AbortController`
3. The narration queue and stream buffer are cleared
4. An interrupt timestamp is recorded so any stale async callbacks are dropped
5. State resets to LISTENING

Interim speech results trigger interrupt before the user even finishes their
word, so the perceived latency is near-zero.

### Text + Speech Sync

The engine tracks `spokenIndex` and `renderedIndex` so the UI knows how much
text has been spoken vs displayed. Each micro-chunk advances `spokenIndex` on
utterance completion. The `onSyncUpdate` callback fires after every spoken
segment.

### Hindi TTS (First-Class)

Hindi is a first-class voice, not a fallback:

- **Auto-detection**: Devanagari characters (Unicode `U+0900`-`U+097F`) trigger
  Hindi voice selection automatically
- **Mixed language**: text like "Hello नमस्ते world दुनिया" is split into
  segments, each spoken with the correct voice (`en-US` or `hi-IN`)
- **Voice selection**: `pickVoice()` finds the best matching
  `speechSynthesis` voice for the target language, falling back to `en-IN` for
  Hindi if no `hi-IN` voice is available
- **Voice language mode**: users can force Auto, English, or Hindi via voice
  command or `setVoiceLangMode()`. The setting persists in `localStorage`
- **Recognition language**: `recognition.lang` follows the voice language mode
  so Hindi input is recognized natively

### State Transitions

Transitions are validated against an allowlist. Invalid jumps (e.g.
IDLE to SPEAKING) are silently rejected. Debounced transitions
(60-80ms) between PROCESSING/RESPONDING/SPEAKING prevent UI jitter while
keeping interrupts instant (debounce timers are cleared on interrupt).

### Duplicate Prevention

Transcripts are deduplicated within a 3-second window. The `requestLock` flag
prevents overlapping AI requests.

## Voice Commands

English examples:

- `build a website for a school science fair`
- `preview website`
- `what do you think is missing here`
- `review website`
- `add that`
- `fix missing things`
- `explain website`
- `audit website`
- `outline website`
- `sonify website`
- `polish HTML`
- `export website`
- `reset session`
- `add heading About Us`
- `add paragraph Welcome students`
- `add button Join now`
- `pause voice`
- `resume voice`
- `stop speaking`
- `voice language Hindi`
- `voice language English`
- `voice language auto`

Hindi/Hinglish examples:

- `school annual day ke liye website banao`
- `preview website`
- `website samjhao`
- `website kaisi dikhti hai`
- `isme kya missing hai`
- `woh add karo`
- `website sonify karo`
- `HTML polish karo`
- `pause voice`
- `resume voice`
- `भाषा Hindi`

## AI Configuration

Use xAI/Grok:

```text
XAI_API_KEY=your_xai_key
GROK_API_KEY=your_xai_key
XAI_MODEL=grok-3-mini
```

Groq is also supported:

```text
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
```

API keys are read from server environment variables. The browser app does not
accept or persist user-supplied provider keys at runtime.

Cloud AI can be disabled for offline-style demos:

```text
AI_CLOUD_ENABLED=0
```

The older `GEMINI_ENABLED=0` flag is still accepted as a compatibility alias,
but new deployments should use `AI_CLOUD_ENABLED`.

## Security

### Session Security

For local development, CodeUp uses a development-only Flask secret if
`FLASK_SECRET_KEY` is not set. For production, set:

```text
CODEUP_ENV=production
FLASK_SECRET_KEY=<long random secret>
SESSION_COOKIE_SECURE=true
```

When `CODEUP_ENV=production`, startup fails without `FLASK_SECRET_KEY`.
`SESSION_COOKIE_SECURE` defaults to true in production and false for local HTTP
development unless explicitly set.

### Content Security Policy

All responses include security headers (`X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`).

Student-hosted pages at `/student-site/` receive a restrictive CSP that blocks
external script and stylesheet loading, prevents form submissions, and limits
framing to same-origin. External `<script src="...">` and `<link>` tags
referencing remote URLs are stripped before serving.

### Cross-Origin Protection

Mutating requests (POST/PUT/DELETE/PATCH) are validated against the `Origin`
or `Referer` header. Requests from unlisted origins are rejected with 403.
Additional allowed origins can be configured via the `ALLOWED_ORIGINS`
environment variable (comma-separated).

## Quickstart

Requirements: Python 3.10 or newer.

```text
git clone https://github.com/da-taki/CodeUp-web.git
cd CodeUp-web
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Development

Install dev dependencies:

```text
pip install -r requirements-dev.txt
```

### Running Tests

```text
python -m pytest -q --timeout=120
```

The test suite covers backend routes, session security, project/version
persistence, storage layout, cleanup logic, ZIP export, parser-backed audits,
guided autofix snapshots, typed models, streaming, smart memory, voice engine
state machine, Hindi detection, mixed-language splitting, micro-chunk
extraction, interrupt behavior, duplicate prevention, concurrency safety, and a
browser-level project/audit/export flow. JS engine tests run via Node `vm`
sandboxes.

Browser E2E uses Playwright. Install the pinned dev dependency, then either
install Playwright Chromium or use an installed Chrome/Edge browser:

```text
pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest tests/test_e2e_browser.py -q --timeout=120
```

### Linting

```text
ruff check codeup/ app.py tests/
ruff format --check codeup/ app.py tests/
```

### Frontend Checks

```text
node --check static/voice-memory-engine.js
node --check static/codeup-html.js
```

### CI

GitHub Actions runs lint, format checks, Python tests, and JS syntax validation
on every push and PR to `main`. See `.github/workflows/ci.yml`.

## Deployment

For production deployment:

1. Set required environment variables:
   ```text
   CODEUP_ENV=production
   FLASK_SECRET_KEY=<generate a long random secret>
   SESSION_COOKIE_SECURE=true
   DATA_DIR=/var/lib/codeup-html
   ```

2. Set at least one AI provider key (or run with `AI_CLOUD_ENABLED=0`).

3. Run behind a reverse proxy (nginx, Caddy) with HTTPS termination.
   The app listens on port 5000 by default.

4. For production WSGI, use gunicorn:
   ```text
   pip install gunicorn
   gunicorn "codeup.app_factory:create_app()" --bind 0.0.0.0:5000
   ```

5. Session artifacts are cleaned up based on `SESSION_ARTIFACT_MAX_AGE`
   (default: 7 days). Project JSON files persist until explicitly removed or
   migrated by an operator.

## Contributing

1. Fork the repo and create a feature branch.
2. Install dev dependencies: `pip install -r requirements-dev.txt`
3. Run `ruff check`, `ruff format --check`, `pytest`, and JS syntax checks
   before submitting a PR.
4. CI must pass before merge.

## Why This Sister Project Exists

The original CodeUp experience taught coding through a different language and
workflow. CodeUp HTML exists so blind and visually impaired students can build
websites directly: the output is visual, local, explainable, reviewable,
exportable, and easy to share in a classroom pilot.

---

*Note: AI assistance was used for portions of the codebase restructuring and
reorganization. The project's main writing, framing, and initial README
direction were authored by me.*
