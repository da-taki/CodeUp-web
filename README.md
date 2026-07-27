# CodeUp Web

CodeUp Web is a voice-first website-building IDE for learning HTML, CSS, and JavaScript. Students can type or speak what they want to build, edit the three source files, preview the website, ask for explanations, check accessibility, save projects, and export a ZIP.

Demo - https://codeup-web.onrender.com/

## Requirements

Use the backend runtime version pinned in the repository. Node.js is used for JavaScript syntax checks during validation. Chrome or Edge is recommended for browser and voice testing.

## Run Locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
py app.py
```

Open `http://127.0.0.1:5000/`.

## What Students Can Do

Students can generate a site, edit `index.html`, `style.css`, and `script.js`, preview desktop/tablet/mobile layouts, ask for a code map, explain files, run/debug the website, check and fix accessibility, save/open projects, use a guided tutorial, and export their work.

## Command Examples

### Build Websites

- `make a website for my school robotics club`
- `build a website for music class`
- `make a simple website for a bakery`
- `create a landing page for tuition center`
- `build a portfolio site for student developer`
- `make a quiz app`
- `make a quiz app about web accessibility basics`
- `create a multi page website`
- `use the science project template`

### Edit Websites

- `add an about section`
- `add a contact section`
- `add a contact form`
- `add a button`
- `add a button named Join Team`
- `add a hero section`
- `add a card section`
- `add navigation`
- `change the title`
- `change the background color`
- `make it simpler`
- `make it professional`
- `make it more beautiful`
- `make it more futuristic`
- `improve the design`
- `add dark mode`
- `turn on high contrast`
- `make the heading bigger`
- `center the section text`
- `make the buttons rounded`
- `add JavaScript interactivity`
- `make it use a function`
- `add comments`

### Understand The Website

- `explain HTML`
- `explain CSS`
- `explain JavaScript`
- `explain JS`
- `explain the code`
- `explain website`
- `summarize the website`
- `code map`
- `give me a code map`
- `project map`
- `describe preview`
- `outline website`
- `read the code`
- `read the HTML`
- `read the CSS`
- `read the JavaScript`
- `what is a div`

### Test And Debug

- `run website`
- `run preview`
- `preview website`
- `debug website`
- `debug this website`
- `find problems`
- `analyze the code`
- `explain error`
- `fix the code`
- `polish HTML`

### Accessibility

- `check accessibility`
- `audit`
- `audit website`
- `accessibility audit`
- `fix accessibility`
- `fix accessibility issues`
- `apply safe fixes`
- `make it accessible`
- `is this ready to share`
- `readiness`
- `screen reader tour`
- `test keyboard navigation`

### Walkthrough

- `walk me through this page`
- `audio accessibility walkthrough`
- `read the page structure`
- `start keyboard journey`
- `next interactive element`
- `previous interactive element`
- `pause on accessibility issues`
- `list accessibility watchpoints`
- `explain first issue`
- `why is this inaccessible`
- `fix this issue`
- `compare accessibility before and after`
- `stop walkthrough`

### Review Changes

- `what changed`
- `read before and after`
- `explain this change`
- `is this risky`
- `add that`
- `apply`
- `go back two steps`

### Projects And Files

- `save project`
- `open project`
- `projects`
- `new project`
- `start over`
- `reset workspace`
- `export website`
- `export zip`
- `export`
- `download`
- `open preview`
- `version history`

### Help And Learning

- `help`
- `commands`
- `show commands`
- `list of commands`
- `what can I do here`
- `start tutorial`
- `tutorial`
- `start HTML tutorial`
- `start CSS tutorial`
- `start JavaScript tutorial`
- `start accessibility tutorial`
- `hint`
- `next`
- `next step`
- `repeat`
- `recap`
- `exit tutorial`

### Voice And Settings

- `stop`
- `stop everything`
- `cancel`
- `stop speaking`
- `pause voice`
- `resume voice`
- `voice on`
- `voice off`
- `set wake word to [word]`
- `voice language`
- `speech language`

## Safety

Hosted student previews strip remote scripts and remote stylesheets, serve only safe local source files, and use a restrictive content security policy. The main app also enforces same-origin checks for write requests.

## AI use declaration
AI was used in this project.

The frontend was heavily AI-assisted. Vibe coded, basically.
