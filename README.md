# CodeUp Web

CodeUp Web is a voice-first website-building IDE for learning HTML, CSS, and JavaScript. Students can type or speak what they want to build, edit the three source files, preview the website, ask for explanations, check accessibility, save projects, and export a ZIP.

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

## Render Deployment

The repository includes `render.yaml`. Render installs `requirements.txt` and starts the app with Gunicorn. Set AI provider keys in Render when cloud generation is needed; without keys, deterministic local fallbacks still keep the website builder usable.

## What Students Can Do

Students can generate a site, edit `index.html`, `style.css`, and `script.js`, preview desktop/tablet/mobile layouts, ask for a code map, explain files, run/debug the website, check and fix accessibility, save/open projects, use a guided tutorial, and export their work.

## Safety

Hosted student previews strip remote scripts and remote stylesheets, serve only safe local source files, and use a restrictive content security policy. The main app also enforces same-origin checks for write requests.
