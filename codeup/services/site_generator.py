"""Deterministic, offline-capable generator for complete 3-file websites.

This module powers CodeUp-Web's website generation when no cloud AI key is
configured (the default demo mode) and also provides the parseable FILE-format
parser used to split AI responses into separate HTML, CSS, and JavaScript
editors.

The generated sites are intentionally rich: every site ships a hero, an about /
mission section, a filterable projects/features grid, animated achievement
stats, a team section, a facilities/equipment grid, an upcoming-events list, and
an accessible join/contact form. All visuals use gradients, CSS shapes, and
emoji so there are never broken external assets.
"""

from __future__ import annotations

import re
from html import escape

# --------------------------------------------------------------------------- #
# Topic detection and naming helpers
# --------------------------------------------------------------------------- #

_KIND_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("robotics", ("robot", "robotics", "stem", "engineering", "maker", "tech club", "coding club", "ai lab")),
    ("food", ("bakery", "cafe", "coffee", "restaurant", "food", "pizza", "kitchen", "bake", "patisserie")),
    ("portfolio", ("portfolio", "resume", "cv", "personal site", "freelance", "designer", "developer", "photographer")),
    ("school", ("school", "college", "class", "annual day", "science fair", "club", "fest", "event", "charity")),
    ("business", ("startup", "company", "agency", "business", "product", "saas", "service", "shop", "store")),
)

_PALETTES: dict[str, tuple[str, str, str]] = {
    # kind: (brand, accent, hero-gradient-end)
    "robotics": ("#6d28d9", "#06b6d4", "#0ea5e9"),
    "food": ("#b91c1c", "#f59e0b", "#ef4444"),
    "portfolio": ("#2563eb", "#10b981", "#6366f1"),
    "school": ("#0f766e", "#f59e0b", "#0891b2"),
    "business": ("#4338ca", "#f43f5e", "#6366f1"),
    "generic": ("#4f46e5", "#06b6d4", "#7c3aed"),
}


def detect_kind(prompt: str) -> str:
    lowered = (prompt or "").lower()
    for kind, keywords in _KIND_PATTERNS:
        if any(keyword in lowered for keyword in keywords):
            return kind
    return "generic"


_STOPWORDS = {"a", "an", "the", "my", "our", "your", "for", "about", "of", "to", "with", "and"}


def brand_title(prompt: str) -> str:
    cleaned = re.sub(r"(?i)\b(build|make|create|generate|design|please|can you)\b", " ", prompt or "")
    cleaned = re.sub(r"(?i)\b(website|web site|site|webpage|web page|landing page|page)\b", " ", cleaned)
    words = [word.strip(" ,.-_!?") for word in cleaned.split() if word.strip(" ,.-_!?")]
    words = [word for word in words if word.lower() not in _STOPWORDS]
    title = " ".join(words[:7]).strip()
    return title.title() if title else "My CodeUp Website"


def topic_phrase(prompt: str) -> str:
    cleaned = re.sub(r"(?i)\b(build|make|create|generate|design)\b", " ", prompt or "")
    cleaned = re.sub(
        r"(?i)\b(a|an|the)?\s*(website|web site|site|webpage|web page|landing page|page)\s*(for|about|of)?\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-_")
    return (cleaned or "your idea")[:80]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "codeup-site"


# --------------------------------------------------------------------------- #
# Content blueprints
# --------------------------------------------------------------------------- #


def _blueprint(kind: str, title: str, topic: str) -> dict:
    """Return a content blueprint. ``title`` and ``topic`` are plain text."""

    base = {
        "tagline": f"A modern, accessible home for {topic} — built for everyone, on every device.",
        "hero_badges": ["Accessible by design", "Mobile friendly", "Built with CodeUp"],
        "primary_cta": "Get started",
        "secondary_cta": "Explore projects",
        "about_title": "About Us",
        "about_lead": f"We are passionate about {topic}. This page tells our story, shares what we do, and shows how you can be part of it.",
        "about_points": [
            "A clear mission that everyone can understand",
            "Real work you can read about and follow",
            "An open invitation to join and contribute",
        ],
        "mission_title": "Our Mission",
        "mission_body": "We make great work approachable. Everything here is organised with semantic headings, strong colour contrast, and keyboard support so nobody is left out.",
        "projects_title": "Featured Projects",
        "projects_intro": "Filter the projects below to see what interests you most.",
        "filters": [("all", "All"), ("flagship", "Flagship"), ("community", "Community"), ("learning", "Learning")],
        "projects": [
            (
                "Project Aurora",
                "flagship",
                "🚀",
                "Our flagship effort that pushes what the team can do and shows off our best ideas.",
            ),
            (
                "Open Workshop",
                "community",
                "🤝",
                "A welcoming space where newcomers learn the ropes alongside experienced members.",
            ),
            (
                "Skill Builder",
                "learning",
                "📚",
                "Hands-on tutorials and challenges that grow real, practical skills step by step.",
            ),
            (
                "Showcase Night",
                "community",
                "🎉",
                "A regular event where members present progress and celebrate wins together.",
            ),
            (
                "Research Sprint",
                "flagship",
                "🔬",
                "Short, focused bursts where we explore bold new directions and prototypes.",
            ),
            (
                "Mentor Match",
                "learning",
                "🧭",
                "Pairs every beginner with a mentor so help is always one message away.",
            ),
        ],
        "stats_title": "Our Impact",
        "stats": [
            (120, "+", "Active members"),
            (45, "", "Projects shipped"),
            (12, "", "Awards won"),
            (8, "", "Years strong"),
        ],
        "team_title": "Meet the Team",
        "team_intro": "A friendly group of people who make it all happen.",
        "team": [
            ("AR", "Aanya Rao", "Lead Coordinator"),
            ("DM", "Diego Mendes", "Projects Lead"),
            ("FK", "Fatima Khan", "Community Lead"),
            ("LC", "Liam Chen", "Outreach Lead"),
        ],
        "facilities_title": "What We Offer",
        "facilities_intro": "Everything you need to do great work.",
        "facilities": [
            ("🛠️", "Workspace", "A comfortable, well-equipped space to build and collaborate."),
            ("💡", "Resources", "Guides, tools, and templates that help you start fast."),
            ("🌐", "Network", "Connections to people and partners who can help you grow."),
            ("♿", "Access", "Step-free, screen-reader friendly, and welcoming to all."),
        ],
        "events_title": "Upcoming Events",
        "events_intro": "Reserve your spot — every seat is free.",
        "events": [
            ("Sat 21 Jun", "Open House", "Tour the space, meet the team, and see live demos."),
            ("Wed 02 Jul", "Beginner Workshop", "A gentle, hands-on introduction for first-timers."),
            ("Fri 18 Jul", "Showcase Night", "Members present their latest projects to the community."),
        ],
        "join_title": "Join Us",
        "join_lead": "Tell us a little about yourself and we will be in touch. No experience required.",
        "footer_note": f"Made with care for {topic}.",
    }

    if kind == "robotics":
        base.update(
            {
                "tagline": f"Where students design, build, and program the robots of tomorrow. Welcome to {title}.",
                "hero_badges": ["STEM for everyone", "Hands-on builds", "Award-winning team"],
                "primary_cta": "Join the lab",
                "secondary_cta": "See our robots",
                "about_title": "Who We Are",
                "about_lead": f"{title} is a student-run robotics lab where curiosity becomes hardware. We design autonomous robots, compete nationally, and teach the next generation of makers.",
                "about_points": [
                    "Beginner-friendly — no experience needed to start",
                    "Real competition robots built every season",
                    "Mentorship in coding, electronics, and design",
                ],
                "mission_title": "Our Mission",
                "mission_body": "To make robotics accessible to every student. We learn by building, share what we know, and welcome makers of all abilities and backgrounds.",
                "projects_title": "Our Robots & Projects",
                "projects_intro": "Filter by category to explore what the lab has been building.",
                "filters": [
                    ("all", "All projects"),
                    ("autonomous", "Autonomous"),
                    ("combat", "Combat"),
                    ("outreach", "Outreach"),
                ],
                "projects": [
                    (
                        "Pathfinder Rover",
                        "autonomous",
                        "🤖",
                        "A self-driving rover that maps a room and avoids obstacles using ultrasonic sensors.",
                    ),
                    (
                        "Titan Bot",
                        "combat",
                        "⚙️",
                        "Our 15 kg combat robot with a titanium wedge and a spinning weapon, built for the arena.",
                    ),
                    (
                        "Line Racer",
                        "autonomous",
                        "🏁",
                        "A blazing-fast line-following robot tuned with a PID control loop.",
                    ),
                    (
                        "Code Club Kits",
                        "outreach",
                        "🧰",
                        "Starter robot kits we design and donate to local primary schools.",
                    ),
                    (
                        "Gripper Arm",
                        "autonomous",
                        "🦾",
                        "A 4-axis robotic arm that sorts objects by colour with a camera.",
                    ),
                    (
                        "Workshop Tour",
                        "outreach",
                        "🎓",
                        "Free weekend workshops that teach soldering, coding, and CAD to beginners.",
                    ),
                ],
                "stats_title": "By the Numbers",
                "stats": [
                    (24, "", "Active members"),
                    (18, "", "Trophies won"),
                    (30, "+", "Robots built"),
                    (7, "", "Years competing"),
                ],
                "team_title": "Our Student Team",
                "team_intro": "Captains and leads who keep the lab running.",
                "team": [
                    ("MA", "Maya Arora", "Team Captain"),
                    ("JT", "Jordan Tan", "Software Lead"),
                    ("RS", "Ravi Sharma", "Mechanical Lead"),
                    ("EB", "Ella Brooks", "Electronics Lead"),
                ],
                "facilities_title": "Equipment & Facilities",
                "facilities_intro": "The tools that turn ideas into working robots.",
                "facilities": [
                    ("🖨️", "3D Printers", "Three FDM printers for rapid prototyping of custom parts."),
                    ("🔌", "Electronics Bench", "Soldering stations, microcontrollers, sensors, and motors."),
                    ("🪚", "CNC & Workshop", "A CNC router and hand tools for machining metal and wood."),
                    ("🏟️", "Practice Arena", "A full-size practice field to test drive and tune robots."),
                ],
                "events_title": "Upcoming Events",
                "events_intro": "Come build with us — every session is free for students.",
                "events": [
                    ("Sat 21 Jun", "Open Lab Day", "Tour the lab, drive a robot, and meet the team."),
                    ("Wed 02 Jul", "Beginner Build Night", "Build your first motorised robot from a kit."),
                    ("Fri 18 Jul", "Regional Qualifier", "Cheer on the team at the regional robotics championship."),
                ],
                "join_title": "Join the Lab",
                "join_lead": "Students of any grade are welcome. Tell us your interests and we will invite you to the next session.",
                "footer_note": f"{title} — student robotics, built for everyone.",
            }
        )
    elif kind == "food":
        base.update(
            {
                "tagline": f"Fresh, handmade, and baked daily with love. Welcome to {title}.",
                "hero_badges": ["Baked fresh daily", "Locally sourced", "Order ahead"],
                "primary_cta": "Order now",
                "secondary_cta": "See the menu",
                "about_title": "Our Story",
                "about_lead": f"{title} began with a simple idea: real ingredients, slow craft, and a warm welcome. Every loaf and pastry is made by hand in small batches.",
                "about_points": [
                    "Sourdough proved for 24 hours",
                    "Seasonal, local ingredients",
                    "Vegan and gluten-free options",
                ],
                "mission_title": "Our Promise",
                "mission_body": "Great taste should be easy to enjoy. Our menu is clearly labelled, our space is step-free, and our team is happy to help with any need.",
                "projects_title": "Menu & Daily Specials",
                "projects_intro": "Filter breads, sweets, drinks, and specials to find your next favourite.",
                "filters": [
                    ("all", "Everything"),
                    ("bread", "Breads"),
                    ("sweet", "Sweets"),
                    ("drinks", "Drinks"),
                    ("special", "Specials"),
                ],
                "projects": [
                    (
                        "Country Sourdough",
                        "bread",
                        "🍞",
                        "A crackly, tangy loaf with an open crumb, proved for a full day.",
                    ),
                    ("Almond Croissant", "sweet", "🥐", "Buttery, flaky layers filled with rich almond cream."),
                    ("Cinnamon Roll", "sweet", "🌀", "Soft, gooey swirls topped with cream-cheese glaze."),
                    ("Flat White", "drinks", "☕", "Velvety microfoam over a double shot of our house espresso."),
                    ("Seeded Rye", "bread", "🌾", "A hearty, wholesome loaf packed with sunflower and pumpkin seeds."),
                    ("Berry Tart", "special", "🫐", "Crisp pastry, vanilla custard, and a pile of fresh berries."),
                ],
                "stats_title": "Reviews & Regulars",
                "stats": [
                    (30, "+", "Recipes"),
                    (5, "", "Bakers"),
                    (1200, "+", "Happy regulars"),
                    (240, "+", "Five-star reviews"),
                ],
                "team_title": "Meet the Bakers",
                "team_intro": "The early risers behind every fresh batch.",
                "team": [
                    ("SM", "Sofia Marín", "Head Baker"),
                    ("TO", "Tomás Okafor", "Pastry Chef"),
                    ("HN", "Hana Nakamura", "Barista Lead"),
                    ("GP", "Grace Park", "Front of House"),
                ],
                "facilities_title": "Why Visit",
                "facilities_intro": "More than just great food.",
                "facilities": [
                    ("🔥", "Stone Oven", "A wood-fired oven that gives our bread its perfect crust."),
                    ("🪑", "Cosy Seating", "A bright, calm space to relax with a coffee and a book."),
                    ("📦", "Click & Collect", "Order ahead online and skip the queue at the counter."),
                    ("♿", "Step-free Access", "An accessible entrance and clearly labelled allergens."),
                ],
                "events_title": "Workshops & Events",
                "events_intro": "Roll up your sleeves and bake with us.",
                "events": [
                    ("Sat 21 Jun", "Sourdough 101", "Learn to make and care for your own starter."),
                    ("Wed 02 Jul", "Kids Pastry Hour", "A fun, hands-on class for young bakers."),
                    ("Fri 18 Jul", "Coffee Cupping", "Taste and compare beans from around the world."),
                ],
                "join_title": "Order or Say Hello",
                "join_lead": "Place a custom order or send us a message. We usually reply the same day.",
                "footer_note": f"{title} — baked fresh, made for everyone.",
            }
        )
    elif kind == "portfolio":
        base.update(
            {
                "tagline": f"Hi, I'm building {topic}. I design and ship thoughtful, accessible work.",
                "hero_badges": ["Open to work", "Accessible-first", "Detail-obsessed"],
                "primary_cta": "Get in touch",
                "secondary_cta": "View my work",
                "about_title": "About Me",
                "about_lead": "I turn ideas into clean, usable products. I care about clear typography, fast performance, and interfaces that work for everyone.",
                "about_points": [
                    "Designs that respect the user",
                    "Code that is readable and tested",
                    "Communication that is clear and kind",
                ],
                "mission_title": "How I Work",
                "mission_body": "Listen first, prototype early, and test with real people. Accessibility and performance are part of the plan, not an afterthought.",
                "projects_title": "Selected Work",
                "projects_intro": "Filter by the kind of work you want to see.",
                "filters": [("all", "All work"), ("web", "Web"), ("design", "Design"), ("writing", "Writing")],
                "projects": [
                    (
                        "Atlas Dashboard",
                        "web",
                        "📊",
                        "A data dashboard with accessible charts and keyboard navigation.",
                    ),
                    ("Brand Refresh", "design", "🎨", "A complete visual identity, from logo to design system."),
                    ("Field Guide", "writing", "✍️", "A long-form guide that makes a hard topic feel simple."),
                    ("Shop Rebuild", "web", "🛒", "A storefront rebuilt for speed, with a 99 Lighthouse score."),
                    (
                        "Motion Study",
                        "design",
                        "🎬",
                        "A set of tasteful micro-interactions that respect reduced motion.",
                    ),
                    ("Docs Overhaul", "writing", "📘", "Developer docs reorganised so answers are easy to find."),
                ],
                "stats_title": "A Few Numbers",
                "stats": [
                    (40, "+", "Projects"),
                    (15, "", "Happy clients"),
                    (6, "", "Years experience"),
                    (100, "%", "On-time delivery"),
                ],
                "team_title": "Kind Words",
                "team_intro": "What people I have worked with say.",
                "team": [
                    ("JL", "Jamie Lee", "“A joy to work with.”"),
                    ("PR", "Priya Rao", "“Shipped early and polished.”"),
                    ("MO", "Marcus Obi", "“Truly cares about users.”"),
                    ("SK", "Sara Kim", "“I'd hire again instantly.”"),
                ],
                "facilities_title": "What I Do",
                "facilities_intro": "Services I offer.",
                "facilities": [
                    ("🧩", "Product Design", "From research and wireframes to polished, tested interfaces."),
                    ("💻", "Front-End Build", "Fast, semantic, accessible code in modern frameworks."),
                    ("🔎", "Accessibility Audit", "Find and fix barriers so everyone can use your product."),
                    ("📝", "Technical Writing", "Clear docs, guides, and content that explain the hard parts."),
                ],
                "events_title": "Availability",
                "events_intro": "Here is what my next few months look like.",
                "events": [
                    ("Jun", "Open for projects", "Taking on one or two new clients this month."),
                    ("Jul", "Workshop", "Running an accessibility workshop for teams."),
                    ("Aug", "Limited slots", "Booking up — reach out early if you're interested."),
                ],
                "join_title": "Let's Work Together",
                "join_lead": "Tell me about your project and I will get back to you within a day.",
                "footer_note": "Designed and built with accessibility in mind.",
            }
        )
    elif kind == "school":
        base.update(
            {
                "tagline": f"Bringing students together for {topic}. Everyone is welcome.",
                "primary_cta": "Sign up",
                "secondary_cta": "See the schedule",
                "filters": [("all", "All"), ("learn", "Learn"), ("create", "Create"), ("celebrate", "Celebrate")],
                "projects_title": "Activities",
                "projects": [
                    ("Quiz Bowl", "learn", "🧠", "A friendly team quiz covering science, history, and pop culture."),
                    ("Art Wall", "create", "🖌️", "A collaborative mural that every student can add to."),
                    ("Talent Show", "celebrate", "🎤", "Singing, dancing, comedy — the stage is yours."),
                    ("Coding Den", "learn", "💻", "Beginner coding sessions with mentors on hand."),
                    ("Maker Corner", "create", "🔧", "Build something with recycled materials and big ideas."),
                    ("Awards Night", "celebrate", "🏅", "Celebrating effort, kindness, and achievement."),
                ],
                "team_title": "Organising Committee",
                "facilities_title": "Good to Know",
                "events_title": "Schedule",
            }
        )
    return base


# --------------------------------------------------------------------------- #
# HTML / CSS / JS rendering
# --------------------------------------------------------------------------- #


def _nav_html() -> str:
    links = [
        ("#about", "About"),
        ("#projects", "Projects"),
        ("#achievements", "Impact"),
        ("#team", "Team"),
        ("#events", "Events"),
        ("#join", "Join"),
    ]
    items = "".join(f'<li><a href="{href}">{label}</a></li>' for href, label in links)
    return items


def _render_html(prompt: str, kind: str, title: str, topic: str, bp: dict) -> str:
    safe_title = escape(title)
    safe_topic = escape(topic)
    safe_prompt = escape(prompt or "")

    badges = "".join(f'<span class="badge">{escape(b)}</span>' for b in bp["hero_badges"])
    about_points = "".join(f"<li>{escape(p)}</li>" for p in bp["about_points"])

    def _filter_button(key: str, label: str, active: bool) -> str:
        pressed = "true" if active else "false"
        return (
            '<button type="button" class="filter-btn" data-filter="'
            + escape(key)
            + '" aria-pressed="'
            + pressed
            + '">'
            + escape(label)
            + "</button>"
        )

    filters = "".join(_filter_button(key, label, i == 0) for i, (key, label) in enumerate(bp["filters"]))
    projects = "".join(
        f'<article class="card" data-category="{escape(cat)}" tabindex="0">'
        f'<div class="card-icon" aria-hidden="true">{icon}</div>'
        f"<h3>{escape(name)}</h3><p>{escape(desc)}</p>"
        f'<span class="tag">{escape(dict(bp["filters"]).get(cat, cat).title())}</span>'
        f"</article>"
        for name, cat, icon, desc in bp["projects"]
    )
    stats = "".join(
        f'<div class="stat"><span class="stat-num" data-count data-target="{target}" data-suffix="{escape(suffix)}">0</span>'
        f'<span class="stat-label">{escape(label)}</span></div>'
        for target, suffix, label in bp["stats"]
    )
    team = "".join(
        f'<article class="member"><div class="avatar" aria-hidden="true">{escape(initials)}</div>'
        f"<h3>{escape(name)}</h3><p>{escape(role)}</p></article>"
        for initials, name, role in bp["team"]
    )
    facilities = "".join(
        f'<article class="facility"><div class="facility-icon" aria-hidden="true">{icon}</div>'
        f"<div><h3>{escape(ftitle)}</h3><p>{escape(desc)}</p></div></article>"
        for icon, ftitle, desc in bp["facilities"]
    )
    events = "".join(
        f'<li class="event"><div class="event-date" aria-hidden="true">{escape(date)}</div>'
        f'<div class="event-body"><h3>{escape(name)}</h3><p>{escape(desc)}</p></div>'
        f'<button type="button" class="btn btn-small" data-signup>Sign up</button></li>'
        for date, name, desc in bp["events"]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(bp["tagline"])}">
  <meta name="codeup-prompt" content="{safe_prompt}">
  <title>{safe_title}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>

  <header class="site-header">
    <div class="container nav-wrap">
      <a class="brand" href="#main">
        <span class="brand-mark" aria-hidden="true">◆</span>
        <span>{safe_title}</span>
      </a>
      <button class="nav-toggle" type="button" data-nav-toggle aria-expanded="false" aria-controls="primary-nav" aria-label="Open menu">☰</button>
      <nav id="primary-nav" class="nav" data-nav aria-label="Primary">
        <ul>{_nav_html()}</ul>
      </nav>
      <button class="theme-toggle" type="button" data-theme-toggle aria-pressed="false" aria-label="Switch to dark mode">🌙 Dark</button>
    </div>
  </header>

  <main id="main">
    <section class="hero" aria-labelledby="hero-heading">
      <div class="container hero-inner">
        <p class="eyebrow">{safe_topic.title() if safe_topic else "Welcome"}</p>
        <h1 id="hero-heading">{safe_title}</h1>
        <p class="hero-tagline">{escape(bp["tagline"])}</p>
        <div class="hero-cta">
          <a class="btn btn-primary" href="#join">{escape(bp["primary_cta"])}</a>
          <a class="btn btn-ghost" href="#projects">{escape(bp["secondary_cta"])}</a>
        </div>
        <div class="badges">{badges}</div>
      </div>
    </section>

    <section id="about" class="section" aria-labelledby="about-heading">
      <div class="container two-col">
        <div>
          <p class="eyebrow">{escape(bp["about_title"])}</p>
          <h2 id="about-heading">{escape(bp["about_title"])}</h2>
          <p class="lead">{escape(bp["about_lead"])}</p>
          <ul class="checklist">{about_points}</ul>
        </div>
        <aside class="panel">
          <h3>{escape(bp["mission_title"])}</h3>
          <p>{escape(bp["mission_body"])}</p>
        </aside>
      </div>
    </section>

    <section id="projects" class="section section-alt" aria-labelledby="projects-heading">
      <div class="container">
        <p class="eyebrow">Explore</p>
        <h2 id="projects-heading">{escape(bp["projects_title"])}</h2>
        <p class="lead">{escape(bp["projects_intro"])}</p>
        <div class="filters" role="group" aria-label="Filter projects">{filters}</div>
        <div class="grid cards" data-cards>{projects}</div>
        <p class="sr-only" role="status" data-filter-status aria-live="polite"></p>
      </div>
    </section>

    <section id="achievements" class="section" aria-labelledby="achievements-heading">
      <div class="container">
        <p class="eyebrow">Achievements</p>
        <h2 id="achievements-heading">{escape(bp["stats_title"])}</h2>
        <div class="stats">{stats}</div>
      </div>
    </section>

    <section id="team" class="section section-alt" aria-labelledby="team-heading">
      <div class="container">
        <p class="eyebrow">People</p>
        <h2 id="team-heading">{escape(bp["team_title"])}</h2>
        <p class="lead">{escape(bp["team_intro"])}</p>
        <div class="grid team-grid">{team}</div>
      </div>
    </section>

    <section id="facilities" class="section" aria-labelledby="facilities-heading">
      <div class="container">
        <p class="eyebrow">Highlights</p>
        <h2 id="facilities-heading">{escape(bp["facilities_title"])}</h2>
        <p class="lead">{escape(bp["facilities_intro"])}</p>
        <div class="grid facilities-grid">{facilities}</div>
      </div>
    </section>

    <section id="events" class="section section-alt" aria-labelledby="events-heading">
      <div class="container">
        <p class="eyebrow">What's on</p>
        <h2 id="events-heading">{escape(bp["events_title"])}</h2>
        <p class="lead">{escape(bp["events_intro"])}</p>
        <ul class="events">{events}</ul>
        <p class="sr-only" role="status" data-signup-status aria-live="polite"></p>
      </div>
    </section>

    <section id="join" class="section" aria-labelledby="join-heading">
      <div class="container narrow">
        <p class="eyebrow">Get involved</p>
        <h2 id="join-heading">{escape(bp["join_title"])}</h2>
        <p class="lead">{escape(bp["join_lead"])}</p>
        <form class="contact-form" data-contact-form novalidate>
          <div class="field">
            <label for="name">Your name</label>
            <input id="name" name="name" type="text" autocomplete="name" required>
          </div>
          <div class="field">
            <label for="email">Email address</label>
            <input id="email" name="email" type="email" autocomplete="email" required>
          </div>
          <div class="field">
            <label for="message">Message</label>
            <textarea id="message" name="message" rows="4" required></textarea>
          </div>
          <button class="btn btn-primary" type="submit">Send message</button>
          <p class="form-status" role="status" data-form-status aria-live="polite"></p>
        </form>
      </div>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container">
      <p>{escape(bp["footer_note"])}</p>
      <p class="muted">Built locally with CodeUp-Web · No tracking · Keyboard friendly</p>
    </div>
  </footer>

  <script src="script.js" defer></script>
</body>
</html>"""


_SITE_CSS = """/* CodeUp-Web generated styles — responsive, accessible, no external assets */
:root {
  color-scheme: light dark;
  --brand: #4f46e5;
  --accent: #06b6d4;
  --hero-end: #7c3aed;
  --bg: #f7f8fc;
  --surface: #ffffff;
  --surface-2: #eef1f8;
  --ink: #14181f;
  --muted: #51607a;
  --line: #dde3ef;
  --ring: #6366f1;
  --radius: 16px;
  --shadow: 0 10px 30px rgba(20, 24, 40, 0.08);
  --maxw: 1080px;
}
[data-theme="dark"] {
  --bg: #0b0f1a;
  --surface: #121829;
  --surface-2: #0f1524;
  --ink: #eef2ff;
  --muted: #a4b1cc;
  --line: #243049;
  --shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: var(--ink);
  background: var(--bg);
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}
.container { width: min(var(--maxw), 92vw); margin: 0 auto; }
.narrow { width: min(640px, 92vw); }
img, svg { max-width: 100%; }
h1, h2, h3 { line-height: 1.15; letter-spacing: -0.02em; }
h2 { font-size: clamp(1.6rem, 4vw, 2.5rem); margin: 0 0 0.4rem; }
p { margin: 0 0 1rem; }
a { color: var(--brand); }
.eyebrow {
  text-transform: uppercase; letter-spacing: 0.14em; font-size: 0.78rem;
  font-weight: 700; color: var(--accent); margin: 0 0 0.35rem;
}
.lead { font-size: 1.1rem; color: var(--muted); max-width: 60ch; }
.muted { color: var(--muted); }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
.skip-link {
  position: absolute; left: 12px; top: -60px; z-index: 100;
  background: var(--brand); color: #fff; padding: 10px 16px; border-radius: 10px;
  transition: top 0.2s ease;
}
.skip-link:focus { top: 12px; }
:focus-visible { outline: 3px solid var(--ring); outline-offset: 3px; border-radius: 6px; }

/* Header / nav */
.site-header {
  position: sticky; top: 0; z-index: 50;
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--line);
}
.nav-wrap { display: flex; align-items: center; gap: 16px; padding: 12px 0; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 800; text-decoration: none; color: var(--ink); font-size: 1.1rem; }
.brand-mark {
  display: grid; place-items: center; width: 32px; height: 32px; border-radius: 9px;
  color: #fff; background: linear-gradient(135deg, var(--brand), var(--accent));
}
.nav { margin-left: auto; }
.nav ul { display: flex; gap: 6px; list-style: none; margin: 0; padding: 0; }
.nav a { text-decoration: none; color: var(--muted); font-weight: 600; padding: 8px 12px; border-radius: 10px; }
.nav a:hover { color: var(--ink); background: var(--surface-2); }
.nav-toggle, .theme-toggle {
  font: inherit; cursor: pointer; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink); border-radius: 10px; padding: 8px 12px; font-weight: 600;
}
.nav-toggle { display: none; margin-left: auto; }
.theme-toggle { white-space: nowrap; }

/* Buttons */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  font: inherit; font-weight: 700; text-decoration: none; cursor: pointer;
  padding: 12px 20px; border-radius: 999px; border: 1px solid transparent; transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.btn:hover { transform: translateY(-2px); }
.btn-primary { color: #fff; background: linear-gradient(135deg, var(--brand), var(--accent)); box-shadow: var(--shadow); }
.btn-ghost { color: var(--ink); background: var(--surface); border-color: var(--line); }
.btn-small { padding: 8px 14px; font-size: 0.9rem; background: var(--surface-2); color: var(--ink); }

/* Hero */
.hero { position: relative; overflow: hidden; color: #fff; padding: clamp(56px, 10vw, 120px) 0; text-align: center;
  background: radial-gradient(1200px 400px at 10% -10%, var(--accent), transparent 60%),
              linear-gradient(135deg, var(--brand), var(--hero-end)); }
.hero-inner { position: relative; }
.hero .eyebrow { color: rgba(255,255,255,0.85); }
.hero h1 { font-size: clamp(2.4rem, 7vw, 4.6rem); margin: 0 0 0.4rem; }
.hero-tagline { font-size: clamp(1.05rem, 2.4vw, 1.4rem); max-width: 62ch; margin: 0 auto 1.6rem; color: rgba(255,255,255,0.92); }
.hero-cta { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
.badges { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin-top: 1.6rem; }
.badge { background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.28); padding: 6px 14px; border-radius: 999px; font-size: 0.85rem; font-weight: 600; }

/* Sections */
.section { padding: clamp(48px, 8vw, 92px) 0; }
.section-alt { background: var(--surface-2); }
.two-col { display: grid; grid-template-columns: 1.4fr 1fr; gap: 32px; align-items: start; }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 24px; box-shadow: var(--shadow); }
.checklist { list-style: none; padding: 0; margin: 1rem 0 0; display: grid; gap: 10px; }
.checklist li { position: relative; padding-left: 30px; }
.checklist li::before { content: "✓"; position: absolute; left: 0; top: 0; width: 20px; height: 20px; display: grid; place-items: center; border-radius: 50%; background: linear-gradient(135deg, var(--brand), var(--accent)); color: #fff; font-size: 0.75rem; }

/* Grid + cards */
.grid { display: grid; gap: 18px; margin-top: 1.6rem; }
.cards { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.card {
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 22px; box-shadow: var(--shadow); transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.card:hover, .card:focus-within { transform: translateY(-4px); box-shadow: 0 18px 40px rgba(20,24,40,0.14); }
.card-icon { font-size: 2rem; }
.card h3 { margin: 0.6rem 0 0.3rem; }
.card p { color: var(--muted); margin-bottom: 0.8rem; }
.tag { display: inline-block; font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--brand); background: color-mix(in srgb, var(--brand) 14%, transparent); padding: 4px 10px; border-radius: 999px; }
.card[hidden] { display: none; }

/* Filters */
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 1.2rem; }
.filter-btn { font: inherit; font-weight: 600; cursor: pointer; padding: 8px 16px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--muted); }
.filter-btn[aria-pressed="true"] { color: #fff; background: linear-gradient(135deg, var(--brand), var(--accent)); border-color: transparent; }

/* Stats */
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 18px; margin-top: 1.6rem; }
.stat { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 26px 18px; text-align: center; box-shadow: var(--shadow); }
.stat-num { display: block; font-size: clamp(2.2rem, 5vw, 3.2rem); font-weight: 800; background: linear-gradient(135deg, var(--brand), var(--accent)); -webkit-background-clip: text; background-clip: text; color: transparent; }
.stat-label { color: var(--muted); font-weight: 600; }

/* Team */
.team-grid { grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }
.member { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 24px; text-align: center; box-shadow: var(--shadow); }
.avatar { width: 72px; height: 72px; margin: 0 auto 12px; border-radius: 50%; display: grid; place-items: center; font-weight: 800; font-size: 1.4rem; color: #fff; background: linear-gradient(135deg, var(--brand), var(--accent)); }
.member h3 { margin: 0 0 0.2rem; }
.member p { color: var(--muted); margin: 0; }

/* Facilities */
.facilities-grid { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.facility { display: flex; gap: 16px; align-items: flex-start; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 22px; box-shadow: var(--shadow); }
.facility-icon { font-size: 1.6rem; width: 48px; height: 48px; flex: none; display: grid; place-items: center; border-radius: 12px; background: var(--surface-2); }
.facility h3 { margin: 0 0 0.3rem; }
.facility p { color: var(--muted); margin: 0; }

/* Events */
.events { list-style: none; margin: 1.6rem 0 0; padding: 0; display: grid; gap: 12px; }
.event { display: flex; align-items: center; gap: 18px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 22px; box-shadow: var(--shadow); }
.event-date { flex: none; font-weight: 800; color: var(--brand); min-width: 90px; }
.event-body { flex: 1; }
.event-body h3 { margin: 0 0 0.2rem; }
.event-body p { color: var(--muted); margin: 0; }
.event[data-done] .btn { background: #16a34a; color: #fff; }

/* Form */
.contact-form { margin-top: 1.6rem; display: grid; gap: 16px; }
.field { display: grid; gap: 6px; }
.field label { font-weight: 600; }
.field input, .field textarea { font: inherit; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); }
.field input:focus, .field textarea:focus { border-color: var(--ring); }
.form-status { font-weight: 600; min-height: 1.2em; margin: 0; }
.form-status[data-state="ok"] { color: #16a34a; }
.form-status[data-state="error"] { color: #dc2626; }

/* Footer */
.site-footer { padding: 40px 0; border-top: 1px solid var(--line); text-align: center; background: var(--surface); }
.site-footer p { margin: 0.2rem 0; }

/* Responsive */
@media (max-width: 760px) {
  .nav-toggle { display: inline-flex; }
  .theme-toggle { order: 3; }
  .nav { position: absolute; left: 0; right: 0; top: 100%; background: var(--surface); border-bottom: 1px solid var(--line); margin: 0; padding: 8px 0; display: none; }
  .nav[data-open] { display: block; }
  .nav ul { flex-direction: column; width: 92vw; margin: 0 auto; }
  .nav a { display: block; }
  .two-col { grid-template-columns: 1fr; }
  .event { flex-direction: column; align-items: flex-start; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  * { animation: none !important; transition: none !important; }
}
"""


_SITE_JS = """/* CodeUp-Web generated interactivity — accessible, dependency-free */
(function () {
  "use strict";
  var root = document.documentElement;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Theme toggle (persisted) */
  var themeBtn = document.querySelector("[data-theme-toggle]");
  function applyTheme(mode) {
    if (mode === "dark") {
      root.setAttribute("data-theme", "dark");
      if (themeBtn) { themeBtn.setAttribute("aria-pressed", "true"); themeBtn.textContent = "\\u2600\\ufe0f Light"; themeBtn.setAttribute("aria-label", "Switch to light mode"); }
    } else {
      root.setAttribute("data-theme", "light");
      if (themeBtn) { themeBtn.setAttribute("aria-pressed", "false"); themeBtn.textContent = "\\ud83c\\udf19 Dark"; themeBtn.setAttribute("aria-label", "Switch to dark mode"); }
    }
  }
  var saved = null;
  try { saved = localStorage.getItem("codeup-site-theme"); } catch (e) {}
  if (!saved && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) saved = "dark";
  applyTheme(saved === "dark" ? "dark" : "light");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try { localStorage.setItem("codeup-site-theme", next); } catch (e) {}
    });
  }

  /* Mobile navigation */
  var navToggle = document.querySelector("[data-nav-toggle]");
  var nav = document.querySelector("[data-nav]");
  function closeNav() {
    if (!nav || !navToggle) return;
    nav.removeAttribute("data-open");
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.setAttribute("aria-label", "Open menu");
  }
  if (navToggle && nav) {
    navToggle.addEventListener("click", function () {
      var open = nav.hasAttribute("data-open");
      if (open) { closeNav(); } else {
        nav.setAttribute("data-open", "");
        navToggle.setAttribute("aria-expanded", "true");
        navToggle.setAttribute("aria-label", "Close menu");
      }
    });
    nav.addEventListener("click", function (e) { if (e.target.closest("a")) closeNav(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeNav(); });
  }

  /* Project filtering */
  var filterBtns = Array.prototype.slice.call(document.querySelectorAll("[data-filter]"));
  var cards = Array.prototype.slice.call(document.querySelectorAll("[data-cards] .card"));
  var filterStatus = document.querySelector("[data-filter-status]");
  filterBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var value = btn.getAttribute("data-filter");
      filterBtns.forEach(function (b) { b.setAttribute("aria-pressed", b === btn ? "true" : "false"); });
      var shown = 0;
      cards.forEach(function (card) {
        var match = value === "all" || card.getAttribute("data-category") === value;
        if (match) { card.removeAttribute("hidden"); shown++; } else { card.setAttribute("hidden", ""); }
      });
      if (filterStatus) filterStatus.textContent = "Showing " + shown + " project" + (shown === 1 ? "" : "s") + ".";
    });
  });

  /* Animated stats */
  var counters = Array.prototype.slice.call(document.querySelectorAll("[data-count]"));
  function runCounter(el) {
    var target = parseInt(el.getAttribute("data-target"), 10) || 0;
    var suffix = el.getAttribute("data-suffix") || "";
    if (reduceMotion) { el.textContent = target + suffix; return; }
    var start = null, duration = 1400;
    function step(ts) {
      if (start === null) start = ts;
      var progress = Math.min((ts - start) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.floor(eased * target) + suffix;
      if (progress < 1) requestAnimationFrame(step); else el.textContent = target + suffix;
    }
    requestAnimationFrame(step);
  }
  if ("IntersectionObserver" in window && counters.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { runCounter(entry.target); io.unobserve(entry.target); }
      });
    }, { threshold: 0.4 });
    counters.forEach(function (c) { io.observe(c); });
  } else {
    counters.forEach(runCounter);
  }

  /* Event sign-up (in-page, no network) */
  var signupStatus = document.querySelector("[data-signup-status]");
  document.querySelectorAll("[data-signup]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var item = btn.closest(".event");
      var name = item ? (item.querySelector("h3") || {}).textContent : "the event";
      btn.textContent = "\\u2713 Signed up";
      btn.disabled = true;
      if (item) item.setAttribute("data-done", "");
      if (signupStatus) signupStatus.textContent = "You're signed up for " + name + ".";
    });
  });

  /* Contact form (validated, no network) */
  var form = document.querySelector("[data-contact-form]");
  if (form) {
    var status = form.querySelector("[data-form-status]");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = new FormData(form);
      var name = (data.get("name") || "").toString().trim();
      var email = (data.get("email") || "").toString().trim();
      var message = (data.get("message") || "").toString().trim();
      var validEmail = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(email);
      if (!name || !validEmail || !message) {
        if (status) { status.textContent = "Please add your name, a valid email, and a message."; status.setAttribute("data-state", "error"); }
        return;
      }
      if (status) { status.textContent = "Thanks, " + name + "! Your message has been received."; status.setAttribute("data-state", "ok"); }
      form.reset();
    });
  }
})();
"""


def _palette_override(kind: str) -> str:
    brand, accent, hero_end = _PALETTES.get(kind, _PALETTES["generic"])
    return f"\n:root {{ --brand: {brand}; --accent: {accent}; --hero-end: {hero_end}; }}\n"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def generate_site_files(prompt: str) -> dict[str, str]:
    """Build a complete, polished 3-file website from a natural-language prompt."""

    kind = detect_kind(prompt)
    title = brand_title(prompt)
    topic = topic_phrase(prompt)
    bp = _blueprint(kind, title, topic)
    html = _render_html(prompt, kind, title, topic, bp)
    css = _SITE_CSS + _palette_override(kind)
    js = _SITE_JS
    return {"html": html, "css": css, "js": js, "title": title}


_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\s*\n?|\n?```\s*$")
_FILE_BLOCK_RE = re.compile(r"FILE:\s*([^\n`]+?)\s*\r?\n(.*?)(?=\r?\nFILE:|\Z)", re.DOTALL | re.IGNORECASE)


def _strip_fences(text: str) -> str:
    body = text.strip()
    body = re.sub(r"^```[a-zA-Z0-9]*\s*\n", "", body)
    body = re.sub(r"\n?```\s*$", "", body)
    return body.strip()


def parse_file_blocks(text: str) -> dict[str, str]:
    """Parse the ``FILE: name`` block format into {html, css, js}.

    Returns only the keys that were found. Unknown file types are ignored.
    """

    result: dict[str, str] = {}
    if not text:
        return result
    for name, body in _FILE_BLOCK_RE.findall(text):
        lowered = name.strip().lower()
        content = _strip_fences(body)
        if not content:
            continue
        if lowered.endswith(".css") or lowered == "css" or "style" in lowered:
            result["css"] = content
        elif lowered.endswith((".js", ".mjs")) or lowered in {"js", "javascript"} or "script" in lowered:
            result["js"] = content
        elif lowered.endswith((".html", ".htm")) or lowered in {"html", "index"}:
            result["html"] = content
    return result


def combine_site_files(html: str, css: str = "", js: str = "", **_ignored: object) -> str:
    """Merge separate HTML/CSS/JS into a single, self-contained document.

    External references to ``style.css`` / ``script.js`` are replaced with the
    inline content so the page works without any sibling files.
    """

    doc = (html or "").strip()
    lowered = doc.lower()
    if "<html" not in lowered:
        doc = (
            '<!doctype html>\n<html lang="en">\n<head>\n'
            '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>CodeUp Site</title>\n</head>\n<body>\n" + doc + "\n</body>\n</html>"
        )

    # Drop external references to the sibling files (they are inlined below).
    doc = re.sub(r'\s*<link\b[^>]*href=["\']?(?:\./)?style\.css["\']?[^>]*>', "", doc, flags=re.IGNORECASE)
    doc = re.sub(r'\s*<script\b[^>]*src=["\']?(?:\./)?script\.js["\']?[^>]*>\s*</script>', "", doc, flags=re.IGNORECASE)

    if css and css.strip():
        style_block = "<style>\n" + css.strip() + "\n</style>"
        # Use a callable replacement so backslash sequences (e.g. \u in JS/CSS)
        # are inserted literally rather than treated as regex escapes.
        if re.search(r"</head\s*>", doc, re.IGNORECASE):
            doc = re.sub(r"</head\s*>", lambda _m: style_block + "\n</head>", doc, count=1, flags=re.IGNORECASE)
        else:
            doc = style_block + "\n" + doc

    if js and js.strip():
        script_block = "<script>\n" + js.strip() + "\n</script>"
        if re.search(r"</body\s*>", doc, re.IGNORECASE):
            doc = re.sub(r"</body\s*>", lambda _m: script_block + "\n</body>", doc, count=1, flags=re.IGNORECASE)
        else:
            doc = doc + "\n" + script_block

    return doc


def generate_combined_site(prompt: str) -> str:
    """Convenience: build the 3 files and return one combined document."""
    files = generate_site_files(prompt)
    return combine_site_files(files["html"], files["css"], files["js"])
