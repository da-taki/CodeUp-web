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

Launch:

```text
$env:AI_CLOUD_ENABLED="0"
python app.py
```

Open `http://127.0.0.1:5000/`, click the command box, then run:

```text
generate a website for a bakery
make it more colorful
add a contact section
read the HTML
give me a code map
stop everything
save snippet as bakery demo
load snippet bakery demo
delete snippet bakery demo
```

## Full robotics-lab demo

Click the command box or press **Voice**. If the browser blocks the microphone,
keep typing the same commands; voice and typed commands use the same routing.

```text
generate a website for the robotics lab of my school with projects, achievements, student team, equipment, events, and a join form
make the design futuristic with dark mode and animated stats
analyze the code
fix the accessibility issues
explain the JavaScript
save snippet as robotics demo
run preview
stop everything
```

The first command produces a complete site with **separate `index.html`,
`style.css`, and `script.js`** loaded into the three editor tabs, plus a live
preview. The generated site includes a hero, an about/mission section, a
filterable projects grid, animated achievement stats, a student team, an
equipment/facilities grid, an upcoming-events list, and an accessible join form.

What to show during the robotics demo:

1. The HTML, CSS, and JavaScript tabs all contain code.
2. **Run Preview** refreshes the iframe.
3. The preview dark-mode toggle works.
4. Project filter buttons hide and show robot cards.
5. Animated stats count up.
6. **Analyze**, **Fix**, **Read Code**, **Code Map**, and **Stop Speaking** work from buttons or commands.

To recover quickly:

- If voice fails, use the text command box.
- If narration keeps going, press **Stop Speaking** or type `stop everything`.
- If the page looks stale, type `run preview`.

---

## CodeUp feature ports

- **Guided Web Tutorial**: `start tutorial`, `continue`, `hint`, `recap`.
- **Web Code Map 2.0**: `give me a code map`, `what CSS styles the hero section`.
- **Mistake Replay**: `compare before and after`, `show changed lines`.
- **Accessibility Watchpoints**: `pause on accessibility issues`.
- **Macros**: `remember this as robotics demo`, `use macro robotics demo`.
- **Bookmarks**: `bookmark this as bakery review`, `read from bookmark bakery review`.
- **Breadcrumbs**: `Alt+B` or `where am I`.
- **Beginner Errors**: `explain this error`, `fix and explain`.
- **Output Diff Narration**: `read only what changed`.

### Simple feature-port demo

```text
generate a website for a bakery
start tutorial
give me a code map
audit website
fix accessibility issues
compare before and after
bookmark this as bakery review
stop everything
```

### Advanced feature-port demo

```text
generate a website for the robotics lab of my school with projects, achievements, student team, equipment, events, and a join form
make the design futuristic with dark mode and animated stats
what JavaScript controls the dark mode button
what CSS styles the hero section
pause on accessibility issues
audit website
fix accessibility issues
compare accessibility before and after
remember this as robotics demo
use macro robotics demo
export website
```

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

### Guided learning and memory

```text
start tutorial
insert page title Demo
continue
hint
recap
exit tutorial
map this website
list all buttons
what CSS styles the hero section
compare before and after
replay my mistake
show changed lines
pause when an image has no alt text
pause when a button has no label
where am I
explain simply
fix and explain
remember this as robotics site
use macro robotics site
list macros
bookmark this as hero section
read from bookmark hero section
list bookmarks
restore my last work
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
