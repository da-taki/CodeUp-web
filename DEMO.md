# CodeUp-Web Demo & Command Catalogue

CodeUp-Web is a blind-first web IDE. Everything below works **two ways**:

1. **Voice** — press the **Voice** button (or say the wake word, default
   `hey codeup`) and speak the command.
2. **Command box** — type the command in the box at the top of the IDE and press
   **Enter** or **Ask / Build**.

Both routes go through the same command parser, so the results are identical.

> Tip: say or type **`stop everything`** (or press **Stop Speaking**) at any time
> to cancel narration instantly.

---

## 60-second demo

```text
generate a website for a bakery
make it more colorful
add a contact section
read the HTML
give me a code map
stop everything
```

## Full robotics-lab demo

```text
generate a website for the robotics lab of my school with projects, achievements, student team, equipment, events, and a join form
make the design futuristic with dark mode and animated stats
analyze the code
fix the accessibility issues
explain the JavaScript
save snippet as robotics demo
```

The first command produces a complete site with **separate `index.html`,
`style.css`, and `script.js`** loaded into the three editor tabs, plus a live
preview. The generated site includes a hero, an about/mission section, a
filterable projects grid, animated achievement stats, a student team, an
equipment/facilities grid, an upcoming-events list, and an accessible join form.

---

## Command reference

### Generate

```text
generate a website for [topic]
make a website about [topic]
create a landing page for [topic]
build a portfolio site for [topic]
```

### Edit the design

```text
make it more beautiful
make it more futuristic
add dark mode
add animations
add a contact section
improve the design
make it accessible
add JavaScript interactivity
fix the code
fix the accessibility issues
```

### Read & understand (accessibility)

```text
read the code
read the HTML
read the CSS
read the JavaScript
explain the code
explain the JavaScript
give me a code map
analyze the code
find problems
summarize the website
outline the website
audit the website
```

### Control

```text
run preview
save snippet as [name]
load snippet
delete snippet [name]
stop everything
stop speaking
cancel
clear command
reset session
```

## Buttons (mouse or keyboard)

Every command above also has a real button in the toolbar:
**Generate, Run Preview, Analyze, Fix, Read Code, Code Map, Audit, Outline,
Save Snippet, Load Snippet, Export, Walkthrough, Reset, Help**, plus
**Stop Speaking**. All controls are keyboard reachable with visible focus
states, and status updates are announced through an `aria-live` region.

## No microphone? No AI key?

- The command box is a full replacement for voice.
- Generation works completely offline: with no AI key configured, a built-in
  deterministic generator produces the same rich, accessible 3-file sites, so
  classroom demos are reliable without any network access.
