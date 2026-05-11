# CodeUp — A Blind-First Python IDE

CodeUp is a Python IDE designed for blind and visually impaired learners. Unlike traditional IDEs that retrofit accessibility on top of visual workflows, CodeUp treats non-visual interaction as the default. Every core feature — navigation, execution, debugging, code understanding — works through audio, keyboard, and natural language commands.

The project is independently developed and intended for use in schools and accessibility programs.

---

## What it does

- **Voice commands** in English and Hindi for navigation, execution, and editing
- **Audio code structure** through sonification — pitch maps to indentation, distinct tones for functions, classes, loops, conditionals
- **Step-by-step execution traces** with spoken playback and a "story mode" narrative
- **Sandboxed Python execution** with subprocess isolation, restricted imports, time and memory caps, AST audit, and same-origin enforcement on state-changing requests
- **Optional AI assistance** (Groq Llama 3.3 70B) for error explanation, code generation, summarization, and a mentor mode with quizzes and bug challenges
- **Audio breakpoint debugger** with variable watching
- **Six-step interactive tutorial** in both English and Hindi covering print, variables, loops, and conditionals

AI assistance is strictly optional. Every core feature works without an API key or network connection.

---

## Accessibility

- Screen reader support via `aria-live` announcer (NVDA, JAWS, VoiceOver)
- Color vision modes (Protanopia, Deuteranopia, Tritanopia)
- High Contrast mode
- Night Mode for low-light environments and users who prefer dark themes
- Dyslexia-friendly mode with Atkinson Hyperlegible font and increased line spacing
- Reduced motion support, both via in-app toggle and the OS-level `prefers-reduced-motion` setting
- Full keyboard navigation — every feature reachable without a mouse
- Press `Escape` at any time to stop speech mid-sentence
- No `window.prompt()` — all dialogs use accessible inline modals with focus management

---

## Quickstart

Requirements: Python 3.8 or newer. The IDE itself runs offline once installed — Monaco, JetBrains Mono, and Atkinson Hyperlegible are all vendored. The landing page additionally requires a one-time Node build to vendor React and bundle the JSX components (see "Building the landing page" below).

Clone and set up a virtualenv:

    git clone https://github.com/da-taki/Code_Up.git
    cd Code_Up
    python -m venv .venv

Activate the virtualenv (Windows PowerShell):

    .\.venv\Scripts\Activate.ps1

Activate the virtualenv (macOS / Linux):

    source .venv/bin/activate

Install dependencies:

    pip install -r requirements.txt

Configure environment:

    cp .env.example .env

Edit `.env` and set at minimum:

    FLASK_SECRET_KEY=<a random secret>
    GROQ_API_KEY=<your free key from https://console.groq.com>

If you don't set a Groq key, AI features return a clear spoken message rather than crashing. To disable AI entirely, set `GEMINI_ENABLED=0`.

### Optional: Offline AI via Ollama

CodeUp can fall back to a locally-running Ollama instance when Groq is unavailable (no internet, no API key, rate-limited). To enable:

1. Install Ollama from <https://ollama.com>
2. Pull a small model: `ollama pull llama3.2:3b`
3. Set environment variables in `.env`:

       OLLAMA_ENABLED=1
       OLLAMA_URL=http://localhost:11434
       OLLAMA_MODEL=llama3.2:3b

When enabled, Groq is tried first; on any failure (network, auth, rate-limit), CodeUp transparently routes to Ollama and prefixes responses with `[offline mode]` so the user knows.

Run the application:

    python app.py

Open `http://127.0.0.1:5000` in Chrome or Edge. (Firefox does not support the Web Speech API for voice input — keyboard and the typed command box still work in any browser.)

Run tests:

    pip install -r requirements-dev.txt
    python -m pytest -q

Tests are fully isolated — snippet storage redirects to a temp directory and no real AI calls are made.

---

## Building the landing page

The IDE at `/ide` works without any Node tooling. The marketing landing page at `/` uses React components that need to be bundled.

First-time setup:

    npm install
    npm run build

This produces:

- `static/vendor/react/react.production.min.js`
- `static/vendor/react/react-dom.production.min.js`
- `static/landing/dist/bundle.js`

After editing any `static/landing/*.jsx` file, rerun `npm run build`. Node is only required for the landing page — running, deploying, or hacking on the IDE never needs it.

If you're deploying to a school environment without Node, the three built files above can be committed to the repo so end users skip the build step entirely.

---
## Architecture

### Backend (`app.py`)

Flask application handling code execution, AST-based analysis, voice intent parsing, and AI proxying. Each `/run` request spawns a fresh subprocess confined to a per-session workspace directory, with restricted built-ins and (on POSIX systems) `RLIMIT_AS` and `RLIMIT_CPU` enforced via `preexec_fn`. Per-session state — execution traces, snippets, sandboxes — is keyed by signed session cookies.

### Frontend

Monaco Editor (vendored locally — no CDN dependency), JavaScript using the Web Speech API for voice recognition and `SpeechSynthesisUtterance` for output, Web Audio API for sonification. Speech recognition language switches automatically between `en-US` and `hi-IN` based on the selected interface language.

### Supporting modules

| File | Purpose |
|---|---|
| `intent_parser.py` | Natural language to structured intent and slots, with Hindi number support |
| `structure_parser.py` | AST-based code structure extraction (functions, classes, loops, async detection, parent class tracking) |
| `sandboxed_fs.py` | Per-session restricted workspace file system |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `FLASK_SECRET_KEY` | Yes | `dev-secret-key-change-in-production` | Signs session cookies |
| `GROQ_API_KEY` | No | — | Enables AI features (get free at console.groq.com) |
| `GEMINI_ENABLED` | No | `1` | Set `0` to disable all AI calls (env var name kept for backward compat) |
| `SESSION_COOKIE_SECURE` | No | `false` | Set `true` behind HTTPS |
| `DATA_DIR` | No | `.` | Directory for per-session snippet files |
| `OLLAMA_ENABLED` | No | `0` | Set `1` to enable local Ollama fallback when Groq fails |
| `OLLAMA_URL` | No | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | No | `llama3.2:3b` | Ollama model name |

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Run code |
| `Escape` | Stop speech immediately |
| `Alt+S` | Sonify current block |
| `Alt+L` | Read current line with context |
| `Alt+V` | List variables in scope |
| `Alt+E` | Check for syntax errors |
| `Alt+H` | Show help / command list |
| `Alt+N` | Next execution trace step |
| `Alt+Left` / `Alt+Right` | Navigate history |
| `Alt+Home` / `Alt+End` | Jump to top / bottom |
| `Ctrl+Shift+P` | Open command palette |
| `Ctrl+Shift+M` | Toggle voice control |
| `Alt+A` | Cycle color vision modes |
| `Alt+D` | Toggle dyslexia mode |
| `Alt+M` | Toggle reduced motion |

---

## Voice Commands

A partial list. Many natural variations work — the intent parser is grammar-based, not exact-match.

| Say | Action |
|---|---|
| "run" / "execute code" | Run code |
| "go to line twenty five" | Navigate to line 25 |
| "read line three" | Read line 3 aloud |
| "what changed here" | Describe variable changes at current trace step |
| "next step" / "previous step" | Step through execution trace |
| "find variable x" | Jump to all usages of variable x |
| "summarize this file" | AI file summary |
| "generate code for fibonacci sequence" | AI code generation |
| "check for errors" | Syntax check plus audio beacon |
| "sonify block" | Hear current block as audio tones |
| "save snippet named hello world" | Save current code |
| "tell the story" | Narrate what your code did |
| "set breakpoint at line 10" | Audio debugger |
| "watch variable x" | Report x at each breakpoint |
| "continue" | Run to next breakpoint |
| "learning mode" | Start mentor / quiz mode |
| "quiz me on loops" | Get a quiz question |
| "explain variables" | Concept explanation |
| "bug challenge" | Find and fix a bug |
| "insert function called greet" | Voice code editing |
| "suggest next line" then "choose 2" | AI autocomplete |
| "help" | List all commands |

Hindi equivalents work for around 15 core commands including `चलाओ` (run), `कोड समझाओ` (analyze), `कोड ठीक करो` (fix), `लाइन बीस पर जाओ` (go to line 20), `मदद` (help). Hindi number words 0–50 are recognized in line-navigation commands.

---

## Sandbox

User code runs in a separate Python subprocess with:

- Restricted imports — only `math`, `random`, `string`, `datetime` allowed
- Restricted built-ins — `eval`, `exec`, `compile`, `open`, `__import__`, and direct module attribute access blocked
- 5-second wall-clock timeout
- 5,000-event trace cap to prevent runaway memory growth
- POSIX-only: 512 MB address space cap and 30-second CPU time cap via `setrlimit`
- Working directory confined to a per-session temp workspace
- `input()` blocked with a clear explanation suggesting hardcoded values

Per-session rate limit: 10 runs per 60 seconds.

---

## Status

v0.8.0 — Deployment ready with full `input()` support, output diff narration, audio heartbeat, voice macros, output bookmarks, code structure breadcrumbs, beginner-mode error explanations, and a coffee-themed UI. Locally tested with the full test suite (200+ passing tests).

### What's new in 0.8.0

- **`input()` support, two ways**:
  - *Pre-flight* (default, reproducible): declare values ahead with the inputs panel, voice (`set inputs to alice and seventeen`), or a magic comment (`# inputs: alice, 17`)
  - *Live* (POSIX only): `say live input mode`, then your code pauses at each `input()` and asks you for the value via voice or typing
- **Output diff narration**: re-run code and hear only what changed, not the whole output again. Voice: `what's different`
- **Audio heartbeat**: soft tone every 500ms while code runs so you know it's alive
- **Voice macros**: `remember this as quick sort` saves the editor as a named macro; `use macro quick sort` loads it
- **Output bookmarks**: `bookmark this` mid-output, then `read from bookmark <name>` later
- **Breadcrumbs**: Alt+B (or `where am i`) reads "function calculate, inside for loop, line 15"
- **Beginner errors**: after an error, say `explain simply` for a jargon-free, real-life-analogy version
- **Auto-save**: every 30 seconds, silently. A draft from the previous session is restored automatically on next visit.
- **Coffee theme**: replaces the previous teal palette with cream, caramel, and espresso

Next:

- User testing with blind students
- Deployment behind HTTPS for non-localhost use
- Research write-up

---

## License

MIT — see `LICENSE`.

---

## Author

Independent project by Taknoor Singh ([@da-taki](https://github.com/da-taki)).