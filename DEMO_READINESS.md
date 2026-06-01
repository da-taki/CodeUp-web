# CodeUp HTML — Demo Readiness Guide

## Windows Setup (One-Time)

```powershell
git clone https://github.com/da-taki/CodeUp-web.git
cd CodeUp-web
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Start in No-Cloud Demo Mode

```powershell
$env:AI_CLOUD_ENABLED="0"
py app.py
```

Open in Chrome or Edge:

```
http://127.0.0.1:5000/
```

No API key or internet connection is required. All features work deterministically
using built-in fallback responses.

## 5-Minute Trainer Demo Flow

The app includes a **"Try this workflow"** panel on the right side of the screen
with clickable steps. A trainer can follow these steps or type/say the commands:

### Step 1: Ask what the tool can do

Type or click: **Hello, what all can I do in here?**

Expected: CodeUp responds with a clear introduction listing all available
features — build, preview, review, audit, export, voice commands, and more.

### Step 2: Build a website

Type or click: **Build a website for my robotics club**

Expected: A complete, accessible HTML website is generated, previewed locally,
and automatically reviewed. The output shows a sighted-guide description and
an accessibility score.

### Step 3: Preview the website

Type or click: **Preview website**

Expected: The website is hosted locally. An iframe preview appears below the
output panel. The "Open local site" link opens the full page in a new tab.

### Step 4: Ask what is missing

Type or click: **What do you think is missing here?**

Expected: CodeUp gives a visual review grounded in the actual current page
content, not generic advice. It names specific missing elements (contact
section, call-to-action, etc.) and suggests what to add next.

### Step 5: Apply the suggestions

Type or click: **Add that**

Expected: CodeUp applies the latest review suggestions, updates the HTML,
republishes the preview, and reviews the improved version. The editor shows
the updated HTML with a new "Next Steps" section.

### Step 6: Audit accessibility

Type or click: **Audit website**

Expected: An accessibility audit runs showing a score out of 100, individual
pass/fail checks, contrast ratios, screen reader transcript preview, and
actionable suggestions. If issues are found, "Fix First Issue" and "Apply
Safe Fixes" buttons become active.

### Step 7: Export the website

Type or click: **Export website**

Expected: A ZIP file downloads containing the website pages and a manifest.
For single-page projects, a standalone HTML file downloads instead.

## Additional Demo Commands

After the main workflow, demonstrate any of these:

| Command | What it does |
|---------|-------------|
| `Explain website` | Audio-friendly description of the page |
| `Outline website` | Shows the heading structure |
| `Sonify website` | Plays different tones for HTML elements |
| `Polish HTML` | Improves accessibility and layout |
| `Reset session` | Clears everything for the next student |

## Project Management

- **Save / Rename**: Enter a name and click "Save / Rename"
- **New Project**: Creates a fresh project
- **Duplicate**: Copies the current project
- **Open**: Switch between saved projects via the dropdown
- **Autosave**: Changes are saved automatically every 700ms
- **Versions**: Each build, review, audit fix, and polish creates a version
  that can be restored

## Voice Demo

1. Click the **Voice Off** button (or press Ctrl+Shift+M)
2. Say: **Build a website for a school science fair**
3. Watch the state change: Listening → Processing → Responding → Speaking
4. While CodeUp is speaking, say a new command to **interrupt** — speech
   stops immediately and the new command executes
5. Test **pause voice** and **resume voice**
6. Test **stop speaking** to silence current narration

If the browser denies microphone access or speech recognition is unavailable,
all commands work identically through the text input field.

### Hindi/Hinglish

- Switch the language dropdown to "Hindi / Hinglish"
- Say: **school annual day ke liye website banao**
- CodeUp responds in Hindi/Hinglish when the language is set to Hindi

## Accessibility Settings

The header provides accessibility controls:

- **Color Vision Mode**: Protanopia, Deuteranopia, Tritanopia, High Contrast
- **Dyslexia Mode**: Larger spacing, Atkinson Hyperlegible font
- **Reduce Motion**: Disables all animations
- **Night Mode**: Dark theme
- **Demo Mode**: Larger text and calmer interface for projector demos

## Reset for Next Student

Type or click: **Reset session**

This clears the current HTML, preview, review memory, and hosted site.
A new project is created automatically.

## Known Limitations

- **No-cloud mode uses deterministic fallbacks**: Generated websites follow a
  fixed template structure. With a cloud AI key configured, websites are more
  varied and creative.
- **Voice recognition requires Chrome or Edge**: Firefox and Safari do not
  support the Web Speech API. The typed command input works in all browsers.
- **Sonification is basic**: Tones represent tag types but do not convey
  content hierarchy or visual layout.
- **Single-session server**: The Flask dev server is designed for one user at
  a time. For multi-user deployment, use gunicorn behind a reverse proxy.
- **No undo for reset**: Once a session is reset, the previous session's
  memory and hosted site are removed. Named projects persist across resets.

## Validation Commands

```powershell
py -m py_compile app.py
py -m pytest -q --timeout=120
py -m ruff check codeup app.py tests
py -m ruff format --check codeup app.py tests
node --check static\codeup-html.js
node --check static\voice-memory-engine.js
```
