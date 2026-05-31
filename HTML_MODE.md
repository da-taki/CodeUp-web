# CodeUp HTML Mode

This project is the HTML website-building edition of CodeUp.

## What Students Do

1. Open `/ide`.
2. Type or say a request such as `Build a website for my school science fair`.
3. Press `Ask / Build`, press `Ctrl+Enter`, or use voice.
4. CodeUp generates a complete single-file HTML website, publishes it locally,
   previews it in the IDE, and explains what was built.
5. Save the work as a named project. Projects persist pages, audit history, and
   server-side versions across browser sessions.

`Ctrl+Enter` previews the current HTML and hosts it at `/student-site/<session>/`.
Hosted session pages are HTML-only: CodeUp serves generated `.html` pages from
the session directory and rejects CSS, JavaScript, image, or nested asset paths.
Keep page CSS and JavaScript inline in the generated HTML.

Publishing replaces the hosted HTML set for the current signed session. If a
student republishes fewer pages, stale generated `.html` files from the earlier
publish are removed from that session directory.

Multi-page projects export through `/export-site.zip`. The ZIP contains
`index.html`, additional normalized page filenames such as `about.html`, and a
small `manifest.json` mapping project page names to exported filenames.

## AI Keys

Set one of these environment variables:

- `XAI_API_KEY` or `GROK_API_KEY` for Grok/xAI.
- `GROQ_API_KEY` for the existing Groq fallback.

Keys are server-side configuration only; HTML mode does not provide a browser
route for students to set provider keys.

Set `AI_CLOUD_ENABLED=0` for deterministic no-key demos. The older
`GEMINI_ENABLED=0` flag still works as a compatibility alias.

## Sessions and Production

Student memory and hosted previews are keyed by a server-generated namespace
stored in Flask's signed session cookie. Do not expose the app in production
without setting `CODEUP_ENV=production` and a long random `FLASK_SECRET_KEY`.
Production mode also defaults `SESSION_COOKIE_SECURE` to true unless overridden.

Runtime files are stored under `instance/data` by default, or under `DATA_DIR`
when configured. The data directory contains `projects/`, `html_memory/`,
`student_sites/`, `exports/`, and `tmp/`. Source checkouts should not contain
runtime JSON, hosted preview files, or exported ZIPs.

Sessions are temporary interaction state. Projects are named persisted entities
with pages, versions, audit history, and exportable artifacts. Browser
sessionStorage is only a cache for responsiveness; project versions are stored
server-side.

## Security

All responses include security headers (CSP, X-Content-Type-Options,
X-Frame-Options, Referrer-Policy). Student-hosted pages receive a restrictive
CSP that blocks external script/stylesheet loading and form submissions.
External `<script src>` and remote `<link>` tags are stripped from generated
HTML before serving.

## Accessibility

Browser speech recognition and speech synthesis are part of the student-facing
HTML mode. Students can build, preview, explain, polish, and sonify a website in
English or Hindi. AI speech is cancelled when a new command starts, and `pause
voice` pauses voice commands.

The accessibility audit returns structured issues with severity, selector,
suggested fix, and autofix availability. Safe autofixes create version
snapshots before and after the edit, then return a deterministic change summary
for the student.
