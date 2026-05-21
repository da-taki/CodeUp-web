# CodeUp HTML

CodeUp HTML is a blind-first website builder for students who want to make real
HTML websites through conversation, keyboard, and voice. It is intentionally
focused on websites: students ask for a site, preview it locally, hear what it
looks like, improve it, audit accessibility, and export the final HTML file.

## Demo Flow

Start the server:

```text
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

Try these prompts:

```text
Hello, what all can I do in here?
Build a website for my robotics club
Preview website
What do you think is missing here?
Audit website
Outline website
Export website
```

## No-Key Demo Mode

CodeUp HTML works even when no cloud AI key is configured. For a deterministic
pilot demo, run:

```text
GEMINI_ENABLED=0 python app.py
```

On Windows PowerShell:

```text
$env:GEMINI_ENABLED="0"
python app.py
```

In this mode, CodeUp still:

- answers what the tool can do,
- builds a complete accessible HTML website,
- hosts the preview locally,
- explains the current site,
- audits accessibility,
- outlines the page structure,
- polishes/wraps HTML,
- exports the website as an `.html` file.

## Student Features

- Conversational AI guide for questions like “what can I do here?”
- Natural-language website generation from “Build a website for ...”
- Local preview at `/student-site/<session-id>/`
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
- Per-session memory for recent prompts, current HTML, and preview URL

## Voice Commands

English examples:

- `build a website for a school science fair`
- `preview website`
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

Cloud AI can be disabled for offline-style demos:

```text
GEMINI_ENABLED=0
```

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
websites directly: the output is visual, local, explainable, exportable, and
easy to share in a classroom pilot.
