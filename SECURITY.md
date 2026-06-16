# Security Policy

CodeUp Web is used by beginners, including blind and visually impaired students,
often in classrooms. Security and safety are core requirements, not extras. This
document describes how the project protects learners and how to report problems.

## Reporting a Vulnerability

Please report security issues privately. Do **not** open a public issue for a
suspected vulnerability.

- Preferred: open a private report through **GitHub Security Advisories** on the
  [`da-taki/CodeUp-web`](https://github.com/da-taki/CodeUp-web/security/advisories)
  repository (the **Security** tab → **Report a vulnerability**).
- Include steps to reproduce, the affected route or file, and the impact you
  observed.

You can expect an acknowledgement and, where the report is valid, a fix or a
clear explanation of why the behavior is intended.

## Safe Generation Guarantees

Generated and edited projects are intended to be safe, beginner-friendly websites
and small apps. The generator and the natural-language editor avoid and validate
against:

- unsafe JavaScript (no `eval`, no inline `on*` handlers injected by generation),
- `eval`-based calculators (the calculator template uses a small, explicit parser),
- credential harvesting or fake login/password flows,
- phishing pages that impersonate real organizations,
- remote tracking scripts and third-party analytics,
- hidden or silent data submission (contact-form templates state clearly that they
  do not transmit data).

Generated `index.html`, `style.css`, and `script.js` are validated before they are
loaded into the editors, and editing actions are validated again before they are
applied.

## Hosted Preview Restrictions

Student previews are served from `/student-site/<session-id>/` and are deliberately
constrained:

- a restrictive **Content Security Policy** blocks external script and stylesheet
  loading, prevents form submissions, and limits framing to same-origin,
- external `<script src="...">` and remote `<link>` tags are stripped before a page
  is served,
- hosted session directories serve generated `.html` pages only; CSS, JavaScript,
  media, and nested asset paths are rejected.

## Application Security

- **Security headers**: all responses include `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`.
- **Cross-origin protection**: mutating requests (POST/PUT/DELETE/PATCH) are
  validated against the `Origin`/`Referer` header and rejected with `403` from
  unlisted origins. Extra origins can be allowed via `ALLOWED_ORIGINS`
  (comma-separated).
- **Session security**: for production, set `CODEUP_ENV=production` and a long
  random `FLASK_SECRET_KEY`; startup fails in production without it.
  `SESSION_COOKIE_SECURE` defaults to true in production.
- **Provider keys are server-side only**: AI provider keys are read from server
  environment variables. The browser app never accepts or persists user-supplied
  provider keys at runtime.
- **Session artifacts** (memory JSON and hosted previews) are cleaned up
  automatically based on `SESSION_ARTIFACT_MAX_AGE` (default: 7 days).

## Scope

This policy covers the CodeUp Web application in this repository. Generated student
projects are educational starters; once exported and hosted elsewhere, their
security is the responsibility of whoever deploys them.
