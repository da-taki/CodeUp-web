# CodeUp HTML Mode

This project is the HTML website-building edition of CodeUp.

## What Students Do

1. Open `/ide`.
2. Type or say a request such as `Build a website for my school science fair`.
3. Press `Ask / Build`, press `Ctrl+Enter`, or use voice.
4. CodeUp generates a complete single-file HTML website, publishes it locally,
   previews it in the IDE, and explains what was built.

`Ctrl+Enter` previews the current HTML and hosts it at `/student-site/<session>/`.
Hosted session pages are HTML-only: CodeUp serves generated `.html` pages from
the session directory and rejects CSS, JavaScript, image, or nested asset paths.
Keep page CSS and JavaScript inline in the generated HTML.

## AI Keys

Set one of these environment variables:

- `XAI_API_KEY` or `GROK_API_KEY` for Grok/xAI.
- `GROQ_API_KEY` for the existing Groq fallback.

## Accessibility

Browser speech recognition and speech synthesis are part of the student-facing
HTML mode. Students can build, preview, explain, polish, and sonify a website in
English or Hindi. AI speech is cancelled when a new command starts, and `pause
voice` pauses voice commands.
