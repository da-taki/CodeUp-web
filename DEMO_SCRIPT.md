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

3. `code map`
   - Shows the HTML landmarks, headings, controls, CSS selectors, and JavaScript behavior.

4. `step narration`
   - Speaks a short walkthrough of how the browser loads the project and how the interaction works.

5. `explain CSS`
   - Explains `style.css` as the visual design file instead of reading raw code only.

6. `add an about section`
   - Updates the current website instead of replacing it.
   - Confirm the original robotics topic is still present.

7. `check accessibility`
   - Shows an accessibility score, issues, why each issue matters, and suggested fixes.

8. `fix accessibility issues`
   - Applies safe deterministic fixes and refreshes the preview.

9. `review project`
   - Summarizes strengths and concrete next improvements.

10. `describe preview`
   - Gives a sighted-guide style summary of what the preview looks like.

11. `export website`
   - Downloads a ZIP with source files plus `README.txt`, `CODE_MAP.txt`, `STEP_NARRATION.txt`, `LEARNING_NOTES.txt`, `PROJECT_SUMMARY.txt`, `ACCESSIBILITY_REPORT.txt`, `PROJECT_REVIEW.txt`, `PREVIEW_DESCRIPTION.txt`, and `manifest.json`.

## App-Type Branch

Use this if you want to show that CodeUp Web can build small apps, not only static websites.

1. `start over`
2. `make a quiz app about Python basics`
3. `add score tracking`
4. `code map`
5. `step narration`
6. `export website`

## Stop Command

Use `stop everything` at any point to cancel speech, listening, and stale async work.
