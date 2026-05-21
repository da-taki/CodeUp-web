# CodeUp HTML

CodeUp HTML is the website-building sister project to the original Python
version of CodeUp. It is built for blind and visually impaired students who want
to create HTML websites with keyboard, screen reader, and voice-first workflows.

Students can type or say requests such as:

```text
Hello, what all can I do in here?
Build a website for my robotics club
Preview website
What do you think is missing here?
```

CodeUp answers like a coding guide, generates a complete single-file HTML
website, hosts it locally, previews it in the IDE, and explains what the website
looks like in English or Hindi.

## What Students Can Do

- Build complete HTML/CSS/JavaScript websites from natural language.
- Have a conversation with the AI about what the tool can do, the current
  website, and what to improve next.
- Preview the current website locally with `Ctrl+Enter` or the `Preview` button.
- Open the hosted website from the local preview link.
- Ask CodeUp to explain what the website looks like and how it is structured.
- Turn on voice control and code hands-free in English or Hindi.
- Say `pause voice` to pause voice commands, then `resume voice` to continue.
- Say `stop speaking` to immediately stop AI narration.
- Sonify the HTML structure so tags become audio cues.
- Add simple elements by voice, such as headings, paragraphs, and buttons.
- Polish the HTML for accessibility and layout improvements.
- Keep per-session memory of the current website, local URL, and recent prompts.

## Voice Commands

Examples in English:

- `build a website for a school science fair`
- `preview website`
- `what do you think is missing here?`
- `explain website`
- `sonify website`
- `polish HTML`
- `add heading About Us`
- `add paragraph Welcome to our club`
- `add button Join now`
- `pause voice`
- `resume voice`
- `stop speaking`
- `help`

Hindi and Hinglish equivalents are supported for the main workflow, including
building, previewing, explaining, sonifying, pausing, and resuming voice.

When a new command is heard, current AI speech is cancelled first so students do
not have to listen over old narration.

## AI Configuration

Set one of these environment variables:

```text
XAI_API_KEY=your_xai_key
GROK_API_KEY=your_xai_key
GROQ_API_KEY=your_groq_key
```

`XAI_API_KEY` or `GROK_API_KEY` uses the xAI/Grok-compatible chat completions
endpoint. `GROQ_API_KEY` remains available as a fallback.

Optional model settings:

```text
XAI_MODEL=grok-3-mini
XAI_API_URL=https://api.x.ai/v1/chat/completions
```

## Quickstart

Requirements: Python 3.8 or newer.

```text
git clone https://github.com/da-taki/CodeUp-web.git
cd CodeUp-web
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

The root URL and `/ide` both open the HTML builder.

## Local Hosting

Every preview saves the student's current HTML to a per-session folder and
serves it at:

```text
/student-site/<session-id>/
```

This is intended for local classroom use: students can build, preview, improve,
and explain their site without leaving the IDE.

## Accessibility

- Screen-reader announcements through `aria-live`.
- Voice recognition in Chrome or Edge.
- English and Hindi speech output.
- Keyboard-first controls.
- Dyslexia-friendly, high-contrast, color-vision, night, and reduced-motion
  modes.
- Audio sonification for HTML structure.
- Speech cancellation when the student starts a new command.

## Development Checks

```text
python -m py_compile app.py
python -m pytest -q
node --check static/codeup-html.js
```
