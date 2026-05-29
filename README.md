# CodeUp HTML

CodeUp HTML is a blind-first website builder for students who want to create
real HTML websites through conversation, keyboard, and voice. This sister
project is focused only on websites: build a page, preview it locally, hear a
visual review, apply improvements, audit accessibility, and export the final
HTML file.

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
- exports the website as an `.html` file.

## Student Features

- Conversational guide for questions like `what can I do here?`
- Natural-language website generation from `Build a website for ...`
- Local preview at `/student-site/<session-id>/`
- Sighted-guide review loop for `what is missing?` and `add that`
- Audio explanation of what the site looks like
- Hindi/Hinglish and English voice workflows
- `pause voice`, `resume voice`, and `stop speaking`
- Speech cancellation when a new command starts
- HTML sonification with different tones for page structure
- Accessibility audit with a score and fix list
- Page outline from headings
- One-click HTML export
- Demo Mode for larger, calmer classroom presentation
- Reset session for the next student
- Per-session memory for recent prompts, current HTML, preview URL, and latest
  visual review

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

## Security Configuration

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

## Quickstart

Requirements: Python 3.8 or newer.

```text
git clone https://github.com/da-taki/CodeUp-web.git
cd CodeUp-web
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Development Checks

```text
python -m py_compile app.py
python -m pytest -q
node --check static/codeup-html.js
```

## Why This Sister Project Exists

The original CodeUp experience taught coding through a different language and
workflow. CodeUp HTML exists so blind and visually impaired students can build
websites directly: the output is visual, local, explainable, reviewable,
exportable, and easy to share in a classroom pilot.
