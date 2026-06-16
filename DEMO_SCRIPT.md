# CodeUp Web 5-Minute Demo Script

## Setup

Run the app locally and open `/ide`.

```powershell
$env:AI_CLOUD_ENABLED="0"
py app.py
```

## Flow

1. `what can I do here`
   - Shows and speaks a short guide for creating, editing, auditing, previewing, and exporting.

2. `make a website for my school robotics club`
   - Generates `index.html`, `style.css`, and `script.js`.
   - Confirm the preview shows a robotics club site with headings, sections, and a join/contact area.

3. `add an about section`
   - Updates the current website instead of replacing it.
   - Confirm the original robotics topic is still present.

4. `check accessibility`
   - Shows an accessibility score, issues, why each issue matters, and suggested fixes.

5. `fix accessibility issues`
   - Applies safe deterministic fixes and refreshes the preview.

6. `export website`
   - Downloads a ZIP with `index.html`, `style.css`, `script.js`, `README.txt`, and `accessibility_report.txt` if an audit has run.

## Stop Command

Use `stop everything` at any point to cancel speech, listening, and stale async work.
