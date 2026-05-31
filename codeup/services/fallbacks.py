from __future__ import annotations

import re

from codeup.services.html_utils import audit_html, wrap_html


def fallback_chat(message: str, html: str, language: str) -> str:
    has_site = bool(html.strip())
    if language == "hi":
        if "missing" in message.lower() or "improve" in message.lower():
            return (
                "Aapki website ko aur strong banane ke liye clear heading, short sections, buttons ke labels, "
                "mobile layout, aur alt text check karein. Preview karein, phir Explain se page ka audio description sun sakte hain."
            )
        return (
            "Yeh CodeUp HTML hai. Aap bol ya type kar sakte hain: build a website for school fair, preview website, "
            "explain website, sonify website, polish HTML, pause voice, resume voice. "
            f"Abhi {'ek website editor mein hai' if has_site else 'aap nayi website bana sakte hain'}."
        )
    if "missing" in message.lower() or "improve" in message.lower():
        return (
            "Check whether the page has a clear title, useful sections, descriptive buttons, mobile spacing, "
            "image alt text, and a strong call to action. Use Preview to inspect it, then Explain for an audio description."
        )
    return (
        "This is CodeUp HTML. You can ask questions, build a website, preview it locally, hear an explanation, "
        "sonify the HTML structure, polish accessibility, and pause or resume voice commands. "
        f"{'There is already a site in the editor.' if has_site else 'Start with: Build a website for my school project.'}"
    )


def fallback_explanation(html: str, language: str) -> str:
    headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, flags=re.IGNORECASE | re.DOTALL)
    clean_headings = [re.sub(r"<[^>]+>", "", h).strip() for h in headings if h.strip()]
    summary = ", ".join(clean_headings[:5]) or "the current page sections"
    if language == "hi":
        return (
            f"Yeh website {summary} par based hai. Page mein structured headings, content sections, aur local preview hai. "
            "Demo ke liye contrast, mobile spacing, button labels, aur image alt text zaroor check karein."
        )
    return (
        f"This website is organized around {summary}. It has a structured page, readable sections, and a local preview. "
        "Before demoing, check contrast, mobile spacing, button labels, and image alt text."
    )


def fallback_review(html: str, language: str) -> str:
    audit = audit_html(html)
    headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, flags=re.IGNORECASE | re.DOTALL)
    clean_headings = [re.sub(r"<[^>]+>", "", h).strip() for h in headings if h.strip()]
    sections = ", ".join(clean_headings[:5]) or "the current page"
    missing: list[str] = []
    lowered = html.lower()
    if "contact" not in lowered:
        missing.append("a contact or next-step section")
    if not re.search(r"<a\b[^>]*>|<button\b", html, re.IGNORECASE):
        missing.append("a clear call-to-action button or link")
    if "schedule" not in lowered and "event" in lowered:
        missing.append("event timing or schedule details")
    if audit.score < 100:
        missing.extend(audit.suggestions[:2])
    if not missing:
        missing.append("real photos with alt text or more specific student details")

    if language == "hi":
        return (
            f"Visual review: website {sections} ke around organized hai. Layout clear hai, sections readable hain, "
            f"aur accessibility score {audit.score}/100 hai. Missing: {', '.join(missing[:3])}. "
            "Aap bol sakte hain: add that, fix missing things, ya make it more polished."
        )
    return (
        f"Visual review: the website is organized around {sections}. It has a clear layout, readable sections, "
        f"and an accessibility score of {audit.score}/100. What is missing: {', '.join(missing[:3])}. "
        "Say or type: add that, fix missing things, or make it more polished."
    )


def fallback_apply_review(html: str, instruction: str, review: str) -> str:
    wrapped = wrap_html(html)
    block = """
    <section aria-labelledby="next-steps-heading">
      <h2 id="next-steps-heading">Next Steps</h2>
      <p>This section was added from the review loop. It gives visitors a clear action after reading the page.</p>
      <ul>
        <li>Add real dates, timings, or contact details for the student project.</li>
        <li>Use descriptive button text so screen reader users understand the action.</li>
        <li>Add images only with useful alt text.</li>
      </ul>
      <a class="button" href="mailto:hello@example.com">Contact the team</a>
    </section>
"""
    if "Next Steps" in wrapped:
        return wrapped
    if re.search(r"</main\s*>", wrapped, flags=re.IGNORECASE):
        return re.sub(r"</main\s*>", block + "\n  </main>", wrapped, count=1, flags=re.IGNORECASE)
    return re.sub(r"</body\s*>", block + "\n</body>", wrapped, count=1, flags=re.IGNORECASE)
