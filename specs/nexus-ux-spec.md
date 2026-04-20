# UX Specification: Project Nexus

> **Version:** 1.7.0
> **Status:** Implemented — Reflects production templates
> **Author:** Ved
> **Last Updated:** 2026-04-19
> **Companion Documents:** [nexus-prd.md](nexus-prd.md) · [nexus-tech-spec.md](nexus-tech-spec.md)

---

## Table of Contents

1. [UX Philosophy](#1-ux-philosophy)
2. [Design Principles](#2-design-principles)
3. [User Journey Maps](#3-user-journey-maps)
4. [First-Run Experience — Browser Setup](#4-first-run-experience--browser-setup)
5. [The Planning Experience — Browser](#5-the-planning-experience--browser)
6. [The Plan — Inline Web Output](#6-the-plan--inline-web-output)
7. [The Decision — Approve / Reject](#7-the-decision--approve--reject)
8. [Post-Trip Feedback — Browser Form](#8-post-trip-feedback--browser-form)
9. [The Weekly Ritual — Habit Design](#9-the-weekly-ritual--habit-design)
10. [Information Architecture & Copy](#10-information-architecture--copy)
11. [Launcher Visual Design](#11-launcher-visual-design)
12. [Web Visual Design System](#12-web-visual-design-system)
13. [Error, Empty & Edge States](#13-error-empty--edge-states)
14. [Accessibility](#14-accessibility)
15. [UX Metrics & Validation](#15-ux-metrics--validation)

---

## 1. UX Philosophy

### 1.1 The Core Promise

**Nexus gives you your Saturday morning back.**

The product exists to eliminate one specific cognitive burden: the 90+ minutes of cross-referencing weather apps, activity databases, restaurant menus, and family preferences that a busy parent repeats every week. Nexus replaces that with a single sentence in and a single yes/no out.

### 1.2 The Feeling

The UX must produce a specific emotional arc:

| Moment | Feeling | Design lever |
|--------|---------|--------------|
| Typing the request | "This is effortless" | One text field, natural language, no flags to remember |
| Watching progress | "It's actually doing all the work I used to do" | Specific, real status updates streaming in real-time — not a spinner |
| Adding a constraint mid-planning | "It's listening to me" | Always-visible input field; system incorporates without restarting |
| Reading the plan | "This is exactly what I would have come up with — but it took me zero effort" | Warm, confident prose; decisions already made |
| Approving | "I trust this" | Every claim is verified, every trade-off explained |
| After the trip | "It just worked" | Plans that survive contact with reality |
| Next Friday | "I should run Nexus" | Habit-forming weekly cadence |

### 1.3 The Invisible System

The user interacts with one smart assistant that happens to be thorough. They never see:

- Internal component names or technical identifiers
- Confidence percentages or scores
- Iteration counts or loop numbers
- Architecture terminology
- Raw data (coordinates, API responses, JSON)

If any of these leak into the user-facing experience, that is a bug.

### 1.4 The Interaction Model

Nexus follows a **request → collaborate → decide** model. The user submits a request, watches live progress, can inject constraints at any time during planning, and receives a finished recommendation to approve, reject with feedback, or redirect.

```
One sentence in → Live progress (with optional mid-planning input) → One decision out
```

The system does 45 minutes of cognitive work in 90 seconds. The user's primary job is judgment, not research — but they can steer the system at any point.

---

## 2. Design Principles

### 2.1 Seven Principles

**1 — One thing at a time.**
Every screen, every prompt, every moment asks the user to do exactly one thing. The plan command takes one sentence. The approval is one button. The rejection is one sentence of feedback. Nexus never presents a menu of options and asks the user to choose — that's the cognitive load it exists to eliminate.

**2 — Decisions, not data.**
Nexus has opinions. It doesn't show the user four options ranked by score and ask them to pick. It recommends one plan, explains why, and mentions what was traded off. The user's role is editorial — approve or redirect — not analytical.

**3 — Show the work, hide the system.**
Users see *what* was checked ("Forecast clear — 5% rain, high of 68°F") but never *how* it was checked ("MeteorologyAgent returned APPROVED with confidence 0.95"). The progress display names real-world tasks, not system components.

**4 — Silence is confidence.**
The plan output doesn't qualify every statement with disclaimers. "Forecast clear" — not "Based on Open-Meteo API data retrieved at 8:14 AM with a 3-hour cache, precipitation probability is 5%, which falls below the 40% threshold." Brevity signals trust. Qualifications appear only when something is genuinely uncertain.

**5 — Earn trust through accuracy, not explanation.**
Users don't trust a plan because the system explained its reasoning in detail. They trust it because the last three plans worked perfectly when they showed up on Sunday morning. Trust is earned over weeks, not demonstrated in a single output. The UX is designed for the repeat user, not the first-timer trying to evaluate the system's competence.

**6 — Friction-free rejection.**
Saying no must be as easy as saying yes. If rejecting a plan requires navigating to a different page, remembering an ID, or explaining exactly what went wrong, the user will just close the tab and plan manually. The rejection path is: click "Not this", type one sentence of what they'd prefer instead, click send. Everything else — re-routing, constraint injection, re-planning — happens automatically.

**7 — Respect the ritual.**
Weekend planning is a weekly ritual. The UX must support the rhythm of that ritual — the Thursday/Friday planning window, the post-trip reflection, the accumulation of family preferences over time. Nexus should feel like a habit, not a tool.

---

## 3. User Journey Maps

### 3.1 Journey 1: First-Time Use

The first-time experience must survive the "Friday evening after a long week" scenario — the user has limited patience and wants to see value before investing effort.

```
┌─────────────────────────────────────────────────────────────────┐
│  FIRST-TIME USER JOURNEY                                        │
│                                                                 │
│  ① Install (2 min)                                              │
│     git clone → uv sync → ollama pull                           │
│     No surprises. Standard tooling.                             │
│                                                                 │
│  ② Launch & Setup (3–5 min)                                     │
│     nexus                                                       │
│     Browser opens. No profile found → redirects to /setup.      │
│     Form-based Q&A — not a config file.                         │
│     "What are your kids' names?" not "Enter YAML array."        │
│     Saves profile.yaml silently.                                │
│                                                                 │
│  ③ First plan (90 sec wait)                                     │
│     Type "family day this weekend" in the browser.              │
│     Progress lines stream in real-time. Plan renders inline.    │
│                                                                 │
│  ④ First approval                                               │
│     Reads plan. Clicks APPROVE button.                          │
│     Markdown saved. Done.                                       │
│                                                                 │
│  ⑤ Value delivered: < 10 minutes from install to approved plan  │
└─────────────────────────────────────────────────────────────────┘
```

**Critical design constraint:** The setup wizard must take under 5 minutes. Every question must feel relevant ("What's your teenager's name?" connects to a real planning need) and the connection to planning value must be immediate ("We ask this so we can find activities they'll actually enjoy").

### 3.2 Journey 2: The Weekly Ritual

This is the primary journey — the one that must be addictive.

```
┌─────────────────────────────────────────────────────────────────┐
│  WEEKLY RITUAL JOURNEY (repeat user)                            │
│                                                                 │
│  Thursday or Friday evening                                     │
│                                                                 │
│  ① Open Nexus (5 sec)                                           │
│     nexus   (or click browser bookmark for localhost)           │
│     Type "beach day Sunday, high protein meal after"           │
│     in the browser input field.                                 │
│                                                                 │
│  ② Watch progress (60–120 sec)                                  │
│     Make coffee while status lines stream in.                   │
│     Each line is a task the user used to do manually.           │
│     "Found 3 beaches matching your preferences" — relief.      │
│     Optionally add a constraint: "avoid Mines Road, potholes"   │
│                                                                 │
│  ③ Review plan (2–3 min reading)                                │
│     Plan renders below progress. Skim the timeline.             │
│     Read "Why Sunday works." Check the backup option.           │
│                                                                 │
│  ④ Approve (2 sec)                                              │
│     Click APPROVE.                                              │
│     "Plan saved — have a great Sunday."                         │
│                                                                 │
│  ⑤ Sunday: Execute the plan                                     │
│     Conditions are good. Restaurant is there. Family is happy.  │
│                                                                 │
│  ⑥ Sunday evening or Monday (2 min)                             │
│     Open Nexus → click on plan → feedback form.                 │
│     "How was it?" Quick reflection. Builds future accuracy.     │
│                                                                 │
│  Total active time: < 5 minutes                                 │
│  vs. 90+ minutes of manual planning                             │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Journey 3: Rejection & Replanning

The user disagrees with the recommendation. This path must be effortless — any friction here means the user abandons Nexus and plans manually.

```
┌─────────────────────────────────────────────────────────────────┐
│  REJECTION JOURNEY                                              │
│                                                                 │
│  ① Plan presented                                               │
│     Las Trampas Wilderness — 6 miles, 1,400 ft                  │
│     (Shorter than goal due to Emma's soccer game)               │
│                                                                 │
│  ② User rejects                                                 │
│     "I'd rather skip the restaurant and do a longer activity"  │
│     Clicks NOT THIS, types one sentence in the feedback input.  │
│                                                                 │
│  ③ System replans (30–60 sec)                                   │
│     New progress lines. Same experience. No forms.              │
│     Feedback is injected as a new constraint automatically.     │
│                                                                 │
│  ④ Revised plan presented                                       │
│     Mt. Diablo — full summit, pack your own lunch.              │
│     "We dropped the restaurant to give you the full climb."     │
│                                                                 │
│  ⑤ Approve                                                      │
│     The system learned. Next time, it may ask upfront.          │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 Journey 4: No Good Plan Exists

Weather is bad all weekend, or constraints are irreconcilable. The system must still be useful — not just shrug.

```
┌─────────────────────────────────────────────────────────────────┐
│  NO-GOOD-PLAN JOURNEY                                           │
│                                                                 │
│  ① Request submitted                                            │
│     "Summit hike this weekend"                                  │
│                                                                 │
│  ② System works... and finds nothing safe                       │
│     Rain Saturday AND Sunday. AQI elevated from fire season.    │
│                                                                 │
│  ③ Plan presented — but honest                                  │
│     "This weekend isn't safe for outdoor summit activities."    │
│     Here's what we found:                                       │
│     • Saturday: heavy rain, outdoor activities affected          │
│     • Sunday: AQI 115 — unhealthy for strenuous activity        │
│                                                                 │
│     Instead, we suggest:                                        │
│     • Lower-intensity outing Sunday AM (AQI better early)        │
│     • Full plan pre-built for next weekend (forecast TBD)        │
│                                                                 │
│  ④ User appreciates honesty over false confidence               │
│     Trust increases. "It saved me from a bad day."              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. First-Run Experience — Browser Setup

### 4.1 Design Goals

The setup flow converts a stranger into a configured user in under 5 minutes. It must feel like a conversation, not a bureaucratic form. Every question connects visibly to planning value.

### 4.2 Setup Flow

When the user runs `nexus` for the first time, the browser opens and detects no profile. The UI redirects to `/setup` — a guided, form-based flow with one question block per screen, inline validation, and clear explanations of why each question matters.

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820/setup                                        │
│                                                              │
│  ┌──────────────────────────────────────────────────┐        │
│  │                                                  │        │
│  │   Welcome to Nexus                               │        │
│  │                                                  │        │
│  │   Let's set up your weekend planning profile.    │        │
│  │   This takes about 3 minutes.                    │        │
│  │                                                  │        │
│  │   Everything stays on your machine — Nexus       │        │
│  │   never sends family data anywhere.              │        │
│  │                                                  │        │
│  │   [ Get Started → ]                              │        │
│  │                                                  │        │
│  └──────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 Question Sequence

The questions are ordered to build momentum — easy personal questions first, then family, then preferences. Each block is a single page in the browser. Inline confirmation appears after each field, and the user can go back to any previous block.

**Block 1 — About You (4 fields, one page)**

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820/setup                                        │
│                                                              │
│  About you                                                   │
│  ─────────                                                   │
│                                                              │
│  What's your name?                                           │
│  ┌──────────────────────────────────┐                        │
│  │ Alex                             │                        │
│  └──────────────────────────────────┘                        │
│                                                              │
│  How would you describe your fitness level?                  │
│  ○ Beginner — Getting started with outdoor activities           │
│  ○ Intermediate — Comfortable with moderate activities          │
│  ● Advanced — Seeking challenges (elevation, distance)          │
│  ○ Elite — Training for endurance events                     │
│                                                              │
│  Any dietary restrictions?                                   │
│  ┌──────────────────────────────────┐                        │
│  │ vegetarian                       │                        │
│  └──────────────────────────────────┘                        │
│  We'll filter restaurants accordingly.                       │
│                                                              │
│  Post-activity protein target? (grams, default: 40g)         │
│  ┌──────────────────────────────────┐                        │
│  │ 40                               │                        │
│  └──────────────────────────────────┘                        │
│                                                              │
│  [ ← Back ]                        [ Next → ]               │
└──────────────────────────────────────────────────────────────┘
```

**Block 2 — Preferred Activities (multi-select, one page)**

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820/setup                                        │
│                                                              │
│  What do you enjoy on weekends?                              │
│  ─────────────────────────────                               │
│  Select all that apply. We'll plan around your picks.        │
│                                                              │
│  ☑ Hiking / Trail running                                    │
│  ☐ Beach / Waterfront                                        │
│  ☐ Park / Picnic / Playground                                │
│  ☑ Biking (road or trail)                                    │
│  ☐ City exploring (walking tours, farmers markets, museums)  │
│                                                              │
│  [ ← Back ]                        [ Next → ]               │
└──────────────────────────────────────────────────────────────┘
```

**Block 3 — Home Base (1 field, one page)**

```
┌──────────────────────────────────────────────────────────────┐
│  Your home base                                              │
│  ──────────────                                              │
│                                                              │
│  Where do you live? (city or address)                        │
│  Used to calculate drive times — never sent to any API.      │
│  ┌──────────────────────────────────┐                        │
│  │ Walnut Creek, CA                 │                        │
│  └──────────────────────────────────┘                        │
│                                                              │
│  [ ← Back ]                        [ Next → ]               │
└──────────────────────────────────────────────────────────────┘
```

**Block 4 — Your Family (dynamic — one member at a time)**

```
┌──────────────────────────────────────────────────────────────┐
│  Your family                                                 │
│  ───────────                                                 │
│  Who goes on weekends with you?                              │
│                                                              │
│  ┌ Family member 1 ──────────────────────────────────┐       │
│  │  Name: [ Sarah          ]   Age: [ 42 ]           │       │
│  │  Interests: [ reading, cafes, moderate walking  ] │       │
│  │  Comfortable outdoor distance: [ 3 ] miles        │       │
│  │  Needs cell service?  ○ Yes  ● No                 │       │
│  │  ✔ Sarah — loves cafes and reading, up to 3 mi    │       │
│  └───────────────────────────────────────────────────┘       │
│                                                              │
│  ┌ Family member 2 ──────────────────────────────────┐       │
│  │  Name: [ Emma           ]   Age: [ 17 ]           │       │
│  │  Interests: [ photography, music, social media  ] │       │
│  │  Comfortable outdoor distance: [ 2 ] miles        │       │
│  │  Needs cell service?  ● Yes  ○ No                 │       │
│  │  ✔ Emma — needs cell service, photography.        │       │
│  └───────────────────────────────────────────────────┘       │
│                                                              │
│  [ + Add another family member ]                             │
│                                                              │
│  [ ← Back ]                        [ Next → ]               │
└──────────────────────────────────────────────────────────────┘
```

**Block 5 — Preferences (2 fields, one page)**

```
┌──────────────────────────────────────────────────────────────┐
│  Preferences                                                 │
│  ───────────                                                 │
│                                                              │
│  Max total driving in a day? (minutes, default: 180)         │
│  ┌──────────────────────────────────┐                        │
│  │ 180                              │                        │
│  └──────────────────────────────────┘                        │
│  That's 3 hours total.                                       │
│                                                              │
│  How many cars do you typically take? (default: 1)           │
│  ┌──────────────────────────────────┐                        │
│  │ 1                                │                        │
│  └──────────────────────────────────┘                        │
│                                                              │
│  [ ← Back ]                        [ Next → ]               │
└──────────────────────────────────────────────────────────────┘
```

**Block 6 — API Keys (optional, one page)**

```
┌──────────────────────────────────────────────────────────────┐
│  API keys                                                    │
│  ────────                                                    │
│  Nexus needs two free API keys to find trails and             │
│  restaurants. Both are free to sign up.                       │
│                                                              │
│  Yelp Fusion (restaurants & menus)                            │
│  ┌──────────────────────────────────────────┐                  │
│  │ ••••••••••••••••••••                        │                  │
│  └──────────────────────────────────────────┘                  │
│  Get a free key at yelp.com/developers                        │
│  [ Test Connection ]  ✔ Connected                              │
│                                                              │
│  Hiking Project (trail data)                                  │
│  ┌──────────────────────────────────────────┐                  │
│  │                                            │                  │
│  └──────────────────────────────────────────┘                  │
│  Get a free key at hikingproject.com/data                     │
│  [ Test Connection ]  ○ Not configured                        │
│                                                              │
│  Keys are saved locally and never sent anywhere               │
│  except the provider’s own API.                               │
│                                                              │
│  [ ← Back ]                        [ Save Profile → ]       │
└──────────────────────────────────────────────────────────────┘
```

> **Design notes:** API key fields use `type="password"` — input is masked. Keys are never displayed after entry; the page only shows "Configured" or "Not set" status. The "Test Connection" button makes a single lightweight API call to validate the key. Keys can be left blank during setup — Nexus will prompt when a missing key is needed during planning.

**Block 7 — Confirmation**

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ✔ Profile saved                                             │
│                                                              │
│  Here's your family:                                         │
│                                                              │
│  Alex (advanced, vegetarian)                                 │
│  Sarah, 42 — cafes, reading, 3 mi max                       │
│  Emma, 17 — photography, shopping, needs cell service        │
│  Jake, 12 — adventure, swimming, 4 mi max                   │
│                                                              │
│  1 car · 3 hr max driving · 40g protein target               │
│                                                              │
│  [ Start Planning → ]                                        │
│                                                              │
│  To edit your profile later, come back to /setup.            │
│  Or edit ~/.nexus/profile.yaml directly.                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 4.4 Setup Design Rules

| Rule | Rationale |
|------|-----------|
| One question block per page | Reduces cognitive load; the user focuses on one topic at a time |
| Confirm each answer inline | Builds momentum; user sees the system understood them |
| Explain *why* for non-obvious questions | "Does Emma need cell service?" → needed for activity location selection |
| Sensible defaults for everything | Most fields have pre-filled defaults the user can accept |
| No jargon | "How far is Sarah comfortable outdoors?" not "Enter comfort_distance_miles" |
| Back button on every page | User can revise any previous answer without starting over |
| Profile summary at end | Confirms everything before first use; catches typos |
| Form validation is inline | Errors appear next to the field, not in a modal or at the top |
| Closing the tab is safe | No partial profile is saved until the user clicks "Save Profile" |

### 4.5 Setup Cancellation & Interruption

| Scenario | UX Behavior |
|----------|-------------|
| **User closes tab mid-setup** | No partial profile saved. Re-opening Nexus redirects to `/setup` again |
| **User navigates away mid-setup** | Same — profile is only saved on explicit "Save Profile" action |
| **User completes setup, wants to change something** | Visit `/setup` — shows current values as defaults with inline editing (see §4.6) |
| **User has no profile, visits `/plan`** | Redirect to `/setup` with message: "Let's set up your profile first — takes about 3 minutes." After setup, redirect back to planning |

### 4.6 Returning to Setup

When the user visits `/setup` again (after initial setup is complete), the page shows the current profile with all fields editable inline:

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820/setup                                        │
│                                                              │
│  Your current profile                                        │
│  ────────────────────                                        │
│                                                              │
│  Alex (advanced, vegetarian, 40g protein)                    │
│  Sarah 42 · Emma 17 · Jake 12                               │
│  Walnut Creek · 1 car · 3 hr driving                        │
│                                                              │
│  What would you like to change?                              │
│                                                              │
│  [ Edit My Details ]  [ Edit Activities ]  [ Edit Family ]  │
│  [ Edit Preferences ]  [ Edit API Keys ]  [ Re-run Full Setup ]                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

This avoids forcing the user through the full wizard to change one detail.

---

## 5. The Planning Experience — Browser

### 5.1 The Input

The user types one natural-language sentence into the planning input field in the browser. No flags, no structured forms, no dropdowns.

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820/plan                                         │
│                                                              │
│  What are you planning this weekend?                         │
│  ┌──────────────────────────────────────────────────┐        │
│  │ beach day Sunday, keep family happy             │        │
│  └──────────────────────────────────────────────────┘        │
│  [ Plan It → ]                                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

The input accepts any phrasing:

- "hard hike Saturday with 3000ft elevation gain, somewhere the kids won't be bored"
- "beach day this Sunday, kids want to swim, I'd like a coastal bike ride"
- "farmers market and park in the city, nothing too strenuous"
- "we have a free Sunday, what's the best option?"
- "same as last week but try somewhere new"
- "something easy, everyone together, not too far"

The CLI shortcut `nexus plan "beach day Sunday"` opens this page with planning already started.

### 5.2 The Wait — 2-Zone Planning Cockpit

The wait is the most critical UX moment. The planning page uses a 2-zone cockpit layout (`body.cockpit`, CSS `grid-template-columns: 42% 1fr`) that keeps the system's work visible at all times.

**Left zone (42%) — Execution graph:**
- SVG visualization of the LangGraph planning graph; each node (parse_intent, draft_proposal, meteorology, family, logistics, nutrition, check_consensus, safety, synthesize_plan, save_plan) lights up as execution reaches it
- Below the graph: request context block (`#inputs-context`) showing the parsed intent, target date, and profile summary

**Right zone (58%) — Live trace and steering:**
- `.context-hero` — large status headline that changes as each phase completes (e.g., "Checking weather...", "Scouting options...", "Plan ready")
- `.agent-queue` — compact scrollable list of agent trace rows; each row shows a dot, agent role, and expandable status body
- `.steer-section` — mid-planning constraint input always visible at the bottom; user can type constraints at any point

**Browser planning cockpit:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  localhost:7820/plan?id=...                              System  Profile │
│                                                                         │
│  ┌────────────────────────────┐  ┌──────────────────────────────────┐   │
│  │   EXECUTION GRAPH (SVG)    │  │  Scouting trail options...       │   │
│  │                            │  │  ← context hero                  │   │
│  │  [parse] → [draft]         │  │                                  │   │
│  │     ↓         ↓            │  │  ──────────────────────────────  │   │
│  │  [meteo] [family][logist]  │  │  ◉  Meteorology                  │   │
│  │     └─────┴────────┘       │  │     Forecast clear, 5% rain      │   │
│  │           ↓                │  │                                  │   │
│  │     [consensus]            │  │  ◉  Logistics                    │   │
│  │           ↓                │  │     Drive times: 25 min / 8 min  │   │
│  │      [safety]              │  │                                  │   │
│  │           ↓                │  │  ◌  Safety review...             │   │
│  │     [synthesize]           │  │                                  │   │
│  │                            │  │  ──────────────────────────────  │   │
│  ├────────────────────────────┤  │  Add a constraint...  [ Send ]   │   │
│  │  Request context           │  │  e.g. "Emma has soccer at 2pm"   │   │
│  │  "hike Sunday, family"     │  └──────────────────────────────────┘   │
│  │  Sun Apr 20 · Alex + 3     │                                         │
│  └────────────────────────────┘                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Mid-planning constraint injection:** The steer input at the bottom of the right zone is always visible during planning. The user can type a constraint at any point (e.g., "actually Emma has soccer at 2pm"). The system incorporates the constraint without restarting from scratch — it injects it into the current LangGraph state and adjusts the in-progress plan. A confirmation appears in the progress stream:

```
  ✔ Plant Power Bistro — vegetarian, high-protein options
  ← You added: "Emma has soccer at 2pm"
  ◌ Adjusting timeline for Emma's soccer game...
```

**Stop planning:** A small "Stop planning" link is available during the progress phase. Clicking it cancels the current run and returns to the input — useful if the user realizes they phrased the request wrong.

### 5.3 Progress Display Design Rules

| Rule | Implementation |
|------|----------------|
| **Real tasks, not system internals** | "Checking Sunday weather..." not "review_meteorology node executing" |
| **Outcomes, not actions** | "Forecast clear — 5% rain" not "Weather API returned 200 OK" |
| **Progressive reveal** | Lines appear one at a time via WebSocket as each check completes |
| **Specific numbers** | "Found 4 options" not "Searching..." → "Done" |
| **Family names in context** | If a check involves a family member, name them: "Finding a spot for Sarah and the kids" |
| **No percentage bars** | The work is discrete tasks, not a continuous process. Checkmarks, not progress bars |
| **Failure is specific** | "Sunday weather: rain expected — trying Saturday..." not "Error in node" |
| **Constraint injection acknowledged** | When the user adds a constraint mid-planning, it appears in the stream with a ← arrow |

### 5.4 Progress States

Each line progresses through three visual states:

```
  ◌ Checking Sunday weather...              ← Active (yellow dot, animated)
  ✔ Forecast clear — 5% rain, high 68°F     ← Complete (green check, detail appended)
  ✘ Sunday weather: rain all day             ← Failed/Constraint (red ✘, reason shown)
```

When a constraint fails and triggers replanning, the progress continues naturally:

```
  ✔ Found 4 options matching your preferences
  ✔ Checking Saturday weather...
  ✘ Saturday: heavy rain expected
  ◌ Trying Sunday instead...
  ✔ Sunday forecast clear — 5% rain, high 68°F
  ✔ Conditions look good
  ...
```

The user sees the system adapting — not failing. The ✘ line is not an error; it's the system doing exactly what the user would do: checking the weather, seeing rain, and trying another day.

### 5.5 Progress Copy Map

Each processing step maps to a user-facing progress message. The messages are written in the language of the task the user would otherwise do manually.

> **Implementation note:** The mapping between internal system events and these messages is defined in the [Technical Specification](nexus-tech-spec.md) §9.3.

| Processing Step | Active State | Completed State (examples) |
|----------------|-------------|---------------------------|
| Intent parsing | Understanding your request... | *(no completed line — instant, not shown)* |
| Trail search | Finding trails matching your fitness goal... | Found 4 trails matching your fitness goal |
| Activity search | Finding activities matching your preferences... | Found 4 options matching your preferences |
| Weather check | Checking {day} weather... | Forecast clear — 5% rain, high 68°F |
| Family activities | Finding a spot for the family nearby... | Downtown Danville — 8 min drive, cell service strong |
| Dining check | Checking restaurants for your post-activity meal... | Plant Power Bistro — vegetarian, high-protein options |
| Drive time check | Calculating drive times... | Drive times checked — 25 min each way |
| Safety check | Final safety check... | Safety check passed |
| Plan generation | Preparing your plan... | Plan ready |

**Loop iteration (rejection → retry):** When the system loops back after a rejection, the activity search message changes to reflect what's being adapted:

| Iteration | Message |
|-----------|---------|
| 1st draft | Finding activities matching your preferences... |
| 2nd draft (weather rejection) | Finding an option with better weather... |
| 2nd draft (family rejection) | Finding an option closer to town... |
| 2nd draft (nutrition rejection) | Finding an option near more restaurants... |
| 3rd+ draft | Trying another option... |

### 5.6 Timing & Pacing

The progress display should feel neither rushed nor stalled. Design targets:

| Phase | Expected Duration | UX Note |
|-------|------------------|---------|
| Intent parsing | < 2 sec | Not shown (too fast to display) |
| Trail/activity search | 2–5 sec | First visible line — sets expectation |
| Weather check | 1–3 sec | Fast and satisfying |
| Family/nutrition/logistics | 2–8 sec each (parallel) | Lines appear as each completes, not all at once |
| Safety check | < 1 sec | Quick confirmation at the end |
| Plan synthesis | 3–8 sec | Last wait before the payoff |
| **Total** | **15–45 sec typical** | **Under the "making coffee" threshold** |

If the total time exceeds 60 seconds (likely on first run when caches are cold), insert a contextual reassurance after the 30-second mark:

```
  ✔ Found 4 options matching your preferences
  ✔ Checking Sunday weather...
  ✔ Forecast clear — 5% rain, high 68°F
  ◌ Finding a spot for the family nearby...
     First run takes a bit longer — building your local cache.
```

This message never appears again once caches are warm.

---

## 6. The Plan — Inline Web Output

### 6.1 Design Philosophy

The plan is the moment of truth. It renders inline in the same browser tab, directly below the progress lines — no page navigation, no file opening, no context switch. It must look like a plan you'd pay a human assistant to create — clear, beautiful, and immediately actionable. It is *not* a dashboard, a report, or a data dump. It is an itinerary.

**Design metaphors:** A thoughtful handwritten note from a trusted friend who researched your weekend. A premium travel itinerary from a concierge service. A morning briefing that respects your time.

### 6.2 Visual Hierarchy

The plan uses a strict visual hierarchy. The user should be able to scan the entire plan in 30 seconds and understand the day. Deep reading is optional.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  LEVEL 1: What and When (scannable in 5 sec)                 │
│  ──────────────────────────────────────────                   │
│  Trail name · Key stats · Date and departure time            │
│  One-line verdict: "Forecast clear. Conditions good."        │
│                                                              │
│  LEVEL 2: Why This Plan (readable in 30 sec)                 │
│  ──────────────────────────────────────────                   │
│  "Why Sunday works" · "What we traded off"                   │
│  The reasoning — warm, brief, confident                      │
│                                                              │
│  LEVEL 3: The Day (the itinerary — 1 min read)               │
│  ──────────────────────────────────────────                   │
│  Timeline from departure to home                             │
│  Who goes where, when, and what they do                      │
│                                                              │
│  LEVEL 4: Backup + Safety (reference only)                   │
│  ──────────────────────────────────────────                   │
│  Backup activity option                                      │
│  Packing checklist · Emergency info                          │
│                                                              │
│  LEVEL 5: Action (the single decision)                       │
│  ──────────────────────────────────────────                   │
│  [ APPROVE THIS PLAN ]   [ NOT THIS — TELL US WHY ]          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 6.3 HTML Plan Template — Editorial Single-Column Layout

The plan page (`body.cockpit`) uses a single editorial column centred in the viewport:

```css
.plan-editorial {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 24px 80px;   /* bottom padding clears the fixed bottom bar */
}
```

Content renders in strict reading order — no columns, no dashboard grid. A fixed top bar (`← Nexus · {date}`) and a fixed bottom bar (`✓ APPROVE · ✕ NOT THIS`) frame the scrollable editorial body.

```
┌─────────────────────────────────────────────────────────────────────┐
│ ← Nexus                                        Sunday, April 19     │  ← fixed top bar
│─────────────────────────────────────────────────────────────────────│
│                                                                     │
│  ┌──────────────────────────────────────── 720px max ───────────┐   │
│  │                                                              │   │
│  │  Mount Diablo Summit                                         │   │  ← h1
│  │  Mitchell Canyon Trail                                       │   │
│  │                                                              │   │
│  │  12.4 mi · 3,100 ft · Strenuous · Depart 7:00 AM            │   │  ← .plan-meta-line.stats-bar
│  │                                                              │   │
│  │  Forecast clear · Trails open · Table confirmed              │   │  ← .plan-verdict-row.verdict-strip
│  │                                                              │   │
│  │  ──────────────────────────────────────────────────────────  │   │  ← <hr>
│  │                                                              │   │
│  │  Why Sunday works                                            │   │  ← why_this_plan
│  │  Saturday has heavy rain — Sunday is clear skies, 68°F.      │   │
│  │  The trailhead is 8 min from Danville — Sarah and the kids   │   │
│  │  have a great spot while you're on the mountain.             │   │
│  │                                                              │   │
│  │  One thing we traded                                         │   │
│  │  This trail hits 89% of your elevation goal.                 │   │
│  │                                                              │   │
│  │  ──────────────────────────────────────────────────────────  │   │
│  │                                                              │   │
│  │  6:30 AM  Leave home (25 min drive)                          │   │  ← day_narrative / timeline
│  │    │                                                         │   │
│  │  7:00 AM  You start the trail                                │   │
│  │    │      Sarah → Danville Books & Brews with Jake.          │   │
│  │    │      Emma: downtown, full cell service.                 │   │
│  │    │                                                         │   │
│  │  ~12:30 PM  You finish                                       │   │
│  │    │        Drive 8 min to Plant Power Bistro.               │   │
│  │    │                                                         │   │
│  │  1:00 PM  Lunch together                                     │   │
│  │    │      Tempeh Power Bowl — vegetarian, high-protein.      │   │
│  │    │                                                         │   │
│  │  2:30 PM  Home                                               │   │
│  │                                                              │   │
│  │  ──────────────────────────────────────────────────────────  │   │
│  │                                                              │   │
│  │  Before you go                                               │   │  ← preparation_checklist
│  │  □ Pack layers and trekking poles                            │   │
│  │  □ Fill water (3L minimum)                                   │   │
│  │  □ Charge everyone's devices                                 │   │
│  │  □ Restaurant opens at 11 AM                                 │   │
│  │                                                              │   │
│  │  Emergency: John Muir Medical Center, 20 min away.           │   │
│  │  Ranger station at trailhead. Cell service at summit.        │   │
│  │                                                              │   │
│  │  ──────────────────────────────────────────────────────────  │   │
│  │                                                              │   │
│  │  If you need a backup                                        │   │  ← backup plan (collapsed)
│  │  Black Diamond Trail via Back Ranch Meadows — similar        │   │
│  │  elevation, Danville access maintained.                      │   │
│  │                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│─────────────────────────────────────────────────────────────────────│
│  ✓ APPROVE                                          ✕ NOT THIS     │  ← fixed bottom bar
└─────────────────────────────────────────────────────────────────────┘
```

**Key CSS classes:**

| Class | Element | Purpose |
|-------|---------|--------|
| `.plan-editorial` | `<div>` wrapper | 720px centred column |
| `.plan-meta-line.stats-bar` | stats row | activity distance/elevation/difficulty/time |
| `.plan-verdict-row.verdict-strip` | verdict row | weather/trail/table status chips |
| `.topbar` | fixed `<div>` | ← Nexus navigation and date |
| `.bottombar` | fixed `<div>` | Approve / Not This buttons |

### 6.4 Content Sections — Detailed Specification

#### 6.4.1 Header

- Plan title: "Your Weekend Plan"
- Date: Full day and date ("Sunday, April 19")
- No branding beyond "Nexus" in footer

#### 6.4.2 Hero Card

The hero card is the 5-second scan. Contains:

| Element | Format | Example |
|---------|--------|---------|
| Activity name | Large, bold | Mount Diablo Summit |
| Activity detail | Smaller, below name | Mitchell Canyon Trail |
| Stats bar | Inline, separated by · | 12.4 mi · 3,100 ft · Strenuous · Depart 7:00 AM |
| Verdict strip | Accent background, brief | Forecast clear · Conditions good · Table confirmed |

**Verdict strip content rules:**
- Maximum 3 phrases, separated by ·
- Each phrase is a verified fact, not an opinion
- Weather always first (most likely reason to abort)
- Never more than one line
- Color: muted green background for all-clear; amber for compromised plan
- When a data point is `estimated` (e.g., cell coverage), append "(est.)" to the phrase: "Cell service likely (est.)"
- When a data point is `cached`, append age: "Forecast clear (2hr cache)"

#### 6.4.3 Why This Plan

Two subsections, each 2–4 sentences:

**"Why {day} works"** — Explains the day/time choice. Mentions what was avoided (rain Saturday, traffic, etc.) and what makes this day work for the family.

**"One thing we traded"** — Only present when trade-offs exist. States plainly what was sacrificed and why. Uses specific numbers ("89% of your elevation goal"). This section builds trust by demonstrating that the system knows what it gave up.

If no trade-offs exist (all goals fully met): this section is replaced with a simple affirmation: "Everything you asked for — no compromises needed."

#### 6.4.4 The Day (Timeline)

A vertical timeline from departure to return:

| Element | Format |
|---------|--------|
| Time | Bold, left-aligned, HH:MM AM/PM |
| Event | Bold headline + 1–2 line description |
| Family context | Who goes where, named specifically |
| Transitions | Drive times and logistics between events |

**Copy rules for the timeline:**
- Use family names, not roles: "Sarah drops you off" not "Your spouse drops you off"
- Use approximate times for activities with variable duration: "~12:30 PM" for hike completion
- Include transition logistics: "Drive 8 min to Plant Power Bistro"
- End with "Home" — closure matters

#### 6.4.5 Backup Plan

- Always present (PRD F9)
- One paragraph: trail name, key stats, why it works as a backup
- Positioned after the main plan so it doesn't compete for attention
- No full itinerary for the backup — just enough to act on if conditions change day-of

#### 6.4.6 Before You Go

A checklist of actionable preparation items. Generated from the plan context:

| Source | Example Item |
|--------|-------------|
| Trail difficulty | Pack layers and trekking poles |
| Duration | Fill water (3L minimum) |
| Family needs | Charge everyone's devices |
| Restaurant hours | Restaurant opens at 11 AM |
| Weather | Sunscreen — UV index 7 |
| Time-sensitive | Parking lot fills by 8 AM on weekends |

**Emergency line:** Always last. Hospital name and distance. Ranger station if available. Cell service status at key points.

#### 6.4.7 Decision Buttons

Two buttons, equal visual weight, clearly labeled. These are native HTML buttons — clicking them sends API requests directly to the localhost server. No clipboard hacks, no workarounds.

| Button | Label | Action |
|--------|-------|--------|
| Approve | APPROVE THIS PLAN | `POST /api/plans/{id}/approve` → saves plan, shows confirmation |
| Reject | NOT THIS — TELL US WHY | Reveals inline feedback input (see §7) |

Buttons are always visible when a plan is pending. On mobile viewports, they stack vertically.

### 6.5 Compromised Plan Output

When the system can't meet all goals, the hero card and "Why" section shift tone:

**Verdict strip:** amber background, honest language.
```
  Shorter than your goal · Weather drives the choice · Everyone together
```

**"What we couldn't do"** replaces "One thing we traded":
```
  This hike is shorter than your goal — about 40% of your target elevation.
  To hit your full summit objective, you'd need a weekend without the
  soccer game. We've already identified April 26–27 as a likely option
  if you want to defer.
```

**Critical rule:** Even a compromised plan is a single recommendation, not a menu. The system picks the best option and explains what was sacrificed. The user approves or rejects — they don't compare.

### 6.6 No-Safe-Plan Output

When safety constraints make all plans unacceptable:

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  THIS WEEKEND ISN'T SAFE FOR SUMMIT HIKING                          │
│                                                                     │
│  Here's what we found:                                              │
│  • Saturday: Heavy rain, 70% chance, trails will be slick           │
│  • Sunday: AQI 115 from wildfire smoke — unhealthy for exertion     │
│                                                                     │
│  ─────────────────────────────────────────────────────               │
│                                                                     │
│  What we can suggest instead                                        │
│                                                                     │
│  Lower-elevation loop                                               │
│  Briones Regional Park — 4 miles, 800 ft, mostly sheltered.         │
│  Doable Sunday morning when AQI is typically lower.                 │
│  Not your summit day, but the family would enjoy it.                │
│                                                                     │
│  ─────────────────────────────────────────────────────               │
│                                                                     │
│  Next weekend looks promising                                       │
│  Early forecast for April 26: clear skies, mild temps.              │
│  We can build your summit plan when the forecast solidifies.        │
│                                                                     │
│  ┌──────────────────────┐   ┌────────────────────────────────┐      │
│  │  PLAN THE LOOP HIKE  │   │  SKIP THIS WEEK                │      │
│  └──────────────────────┘   └────────────────────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

The system still takes initiative. It doesn't just say "no" — it offers a downscaled alternative and a forward-looking suggestion.

---

## 7. The Decision — Approve / Reject

### 7.1 Approval

Approval is one click, zero friction.

Click APPROVE THIS PLAN. The page updates with a confirmation:
```
  ✔ Plan approved — saved to ~/.nexus/plans/2026-04-19-mt-diablo.md

  Have a great Sunday, Alex.
```

**Design notes:**
- The approve button acts on the currently displayed plan — no ID lookup required.
- The Markdown file is saved for Obsidian sync immediately.
- The farewell message uses the day of the plan and the user's name. Small warmth.
- A "View saved plans" link appears below the confirmation.

### 7.2 Rejection

Rejection must be as effortless as approval. The user states what they want differently in natural language — no forms, no structured feedback.

Click NOT THIS — TELL US WHY. A single text input appears inline below the plan:

```
  What would you prefer?
  ┌──────────────────────────────────────────────────┐
  │ I'd rather skip the restaurant and do a longer   │
  │ hike                                             │
  └──────────────────────────────────────────────────┘
  [ REPLAN ]   [ CANCEL ]
```

**After rejection, the system replans inline — same page, no navigation:**
```
  Replanning your weekend...

  ✔ Removing restaurant constraint
  ✔ Found 3 longer trails now available
  ✔ Checking weather for Mt. Tamalpais...
  ✔ Forecast clear — perfect for a full-day hike
  ✔ Safety check passed

  Plan ready
```

The new plan replaces the old one in the same page. The replanning progress display follows the same rules as the initial plan but acknowledges what changed.

### 7.3 Rejection Edge Cases

| Scenario | UX Behavior |
|----------|-------------|
| **User rejects with no feedback** | The feedback input is required — placeholder text: "What would you prefer? (A sentence or two helps us find something better)". The REPLAN button is disabled until text is entered |
| **User rejects with identical feedback twice** | Display: "We tried that direction and hit the same constraints. Try adjusting your profile or planning for a different weekend." Offer links to [Edit Profile] and [Plan Again] |
| **User rejects 5 times in one session** | Display: "This one might need a human touch — try adjusting your constraints or planning manually this week. You can always come back next Friday." Stop replanning. |
| **User closes browser without deciding** | Plan stays pending. Landing page shows it on next visit. No timeout — the user decides when they're ready |

### 7.4 Decision Design Rules

| Rule | Rationale |
|------|-----------|
| One-click approval on the same page | The common case shouldn't require navigation or ID lookup |
| Rejection feedback is free text | The user knows what they want; let them say it naturally |
| Rejection triggers automatic replanning | No manual "replan" step — the system takes the feedback and acts |
| Replanning shows what changed | "Removing restaurant constraint" → "Found 3 longer trails" |
| No "are you sure?" confirmations | Approving a weekend plan is not a destructive action |
| Re-rejection is allowed | If the second plan is also wrong, reject again with new feedback |

---

## 8. Post-Trip Feedback — Browser Form

### 8.1 Purpose

Post-trip feedback closes the loop. It's how the system learns and how the user reflects. It should feel like a 2-minute journal entry, not a survey.

### 8.2 Feedback Flow

The user navigates to a completed plan (via the landing page or `/plans`) and clicks "How did it go?" — a feedback form appears inline on the plan page:

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820/plans/2026-04-19-mt-diablo                   │
│                                                              │
│  How was your weekend?                                       │
│  ──────────────────────                                      │
│                                                              │
│  Sunday, April 19 — Mt. Diablo Summit                        │
│                                                              │
│  How did the plan work out?                                  │
│                                                              │
│    ● Went exactly as planned                                 │
│    ○ Mostly worked, a few surprises                          │
│    ○ Had to change things significantly                      │
│    ○ Didn't end up going                                     │
│                                                              │
│  Anything we should know for next time?                      │
│  (trail conditions, restaurant notes, timing)                │
│  ┌──────────────────────────────────────────────────┐        │
│  │ The parking lot was full by 7:30, had to use     │        │
│  │ overflow. Plant Power Bistro was packed, 20 min  │        │
│  │ wait.                                            │        │
│  └──────────────────────────────────────────────────┘        │
│                                                              │
│  [ Submit Feedback ]                                         │
│                                                              │
│  ✔ Noted — we'll suggest earlier departure and check         │
│    restaurant wait times in future plans.                    │
│                                                              │
│  Thanks, Alex. See you next week.                            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 8.3 Feedback Question Design

The feedback is 2–3 questions maximum. Never a long survey.

| Question | Type | Purpose |
|----------|------|---------|
| How did it go? | Single choice (4 options) | Binary success signal |
| Anything to note? | Free text (optional) | Specific learnings for future plans |
| *(Only if "Had to change things"):* What changed? | Free text | Understand failure modes |

### 8.4 Feedback When Things Went Wrong

If the user selects "Had to change things significantly", an additional field appears:

```
  What changed?
  ┌──────────────────────────────────────────────────┐
  │ Trail was actually closed, had to do the backup  │
  │ trail. The backup was great though.              │
  └──────────────────────────────────────────────────┘
```

Response after submit:
```
  ✔ Noted — we'll check trail closure reports more carefully.
    Glad the backup worked.
```

If "Didn't end up going", an additional field appears:

```
  What happened?
  ┌──────────────────────────────────────────────────┐
  │ Kids had a birthday party, forgot to mention it. │
  └──────────────────────────────────────────────────┘
```

Response:
```
  ✔ Got it. Would calendar integration help catch these?
    That's something we're considering for a future version.
```

### 8.5 Feedback Design Rules

| Rule | Rationale |
|------|-----------|
| Maximum 3 questions | Respect for the user's time on a Sunday evening |
| Always optional free text | Some people want to note things; others don't |
| Acknowledge the feedback concretely | "We'll suggest earlier departure" — not just "Thanks for your feedback" |
| Warm sign-off | "See you next week." Reinforces the ritual. |
| No NPS or rating scales | This is a personal tool, not a SaaS product. The metric is repeat use. |

---

## 9. The Weekly Ritual — Habit Design

### 9.1 Why Habit Design Matters

Nexus is a product that creates value through repetition. A tool used once is a novelty. A tool used every Friday evening is indispensable. The UX must actively support habit formation.

### 9.2 The Habit Loop

```
       ┌──── CUE ──────────────────────────────────┐
       │                                            │
       │  Thursday/Friday: "What are we doing       │
       │  this weekend?" conversation starts.       │
       │                                            │
       └─────────────┬─────────────────────────────-┘
                     │
                     ▼
       ┌──── ROUTINE ──────────────────────────────┐
       │                                            │
       │  Open Nexus in browser. Type one sentence. │
       │  Watch progress. Review plan. Approve.     │
       │  Total: 3–5 minutes.                       │
       │                                            │
       └─────────────┬────────────────────────────-─┘
                     │
                     ▼
       ┌──── REWARD ───────────────────────────────┐
       │                                            │
       │  Saturday morning: no negotiation,         │
       │  no research, no arguments.                │
       │  Everyone knows the plan.                  │
       │  The plan works.                           │
       │                                            │
       └────────────────────────────────────────────┘
```

### 9.3 Ritual-Supporting UX Elements

| Element | Implementation | Habit Function |
|---------|----------------|----------------|
| **Instant start** | `nexus` or browser bookmark — one action, no setup | Zero activation energy |
| **Purposeful wait** | Progress lines streaming in real-time that name real tasks | Makes the system feel valuable, not slow |
| **Beautiful output** | Inline itinerary you'd show your spouse | The plan is the reward, not just data |
| **Easy approval** | One click on the same page | Completing the loop feels satisfying |
| **Warm sign-off** | "Have a great Sunday, Alex." | Emotional closure |
| **Feedback prompt** | Post-trip reflection in 2 minutes | Closes the loop; builds investment |
| **Improving accuracy** | Plans get better over time with feedback | Switching cost increases with use |
| **Saved history** | `~/.nexus/plans/` grows into a trip journal | Personal archive creates attachment |

### 9.4 The Landing Page

The landing page at `localhost:7820` is the lightweight entry point for the ritual. It shows where things stand without requiring a new plan.

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820                                              │
│                                                              │
│  ┌──────────────────────────────────────────────┐            │
│  │  Nexus                                       │            │
│  │                                              │            │
│  │  Pending plan                                │            │
│  │  Sunday, April 19 — Mt. Diablo Summit        │            │
│  │  Awaiting your approval   [ View Plan → ]    │            │
│  │                                              │            │
│  │  Last weekend                                │            │
│  │  April 12 — Las Trampas Wilderness ✔         │            │
│  │  "Went exactly as planned"                   │            │
│  │                                              │            │
│  │  Plans this month: 3                         │            │
│  │  Approval rate: 67% first-pass               │            │
│  │                                              │            │
│  └──────────────────────────────────────────────┘            │
│                                                              │
│  What are you planning this weekend?                         │
│  ┌──────────────────────────────────────────────────┐        │
│  │                                                  │        │
│  └──────────────────────────────────────────────────┘        │
│  [ Plan It → ]                                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

The landing page is a gentle nudge — it reminds the user about a pending plan, shows recent success, and quietly tracks the system's accuracy. The planning input is always available at the bottom. It never nags or sends notifications.

The user can bookmark `localhost:7820` in their browser for instant access — no terminal needed for the weekly ritual.

### 9.5 Plan History

Over time, `~/.nexus/plans/` becomes a trip journal:

```
~/.nexus/plans/
├── 2026-04-05-briones-loop.md
├── 2026-04-12-las-trampas.md
├── 2026-04-19-mt-diablo.md
└── ...
```

Each Markdown file is Obsidian-compatible and contains:
- The full plan as presented
- Weather conditions at time of planning
- Post-trip feedback (appended after submitting feedback via the browser form)

This archive serves three purposes:
1. **Nostalgia:** "Remember that Mt. Diablo hike?" — browseable in Obsidian
2. **Learning:** The system can reference past trips to avoid repeating trails too soon
3. **Switching cost:** The more history, the harder to leave Nexus

---

## 10. Information Architecture & Copy

### 10.1 Voice & Tone

Nexus speaks like a competent, understated assistant. Not a chatbot. Not a corporation. Not a friend trying too hard.

| Attribute | Description | Example |
|-----------|-------------|---------|
| **Confident** | States facts without hedging | "Forecast clear" not "The forecast appears to be clear" |
| **Warm but brief** | Acknowledges the human without over-explaining | "Have a great Sunday, Alex." |
| **Specific** | Uses real numbers and names | "8 min from activity" not "nearby" |
| **Honest** | Admits limitations directly | "This hike is shorter than your goal" |
| **Never cute** | No emoji, no puns, no exclamation marks | "Plan ready." not "Your plan is ready! 🎉" |
| **Never apologetic** | States reality without sorry | "Sunday weather: rain expected" not "Sorry, it looks like..." |

### 10.2 Word List — Preferred vs. Avoided

| Context | Preferred | Avoided |
|---------|-----------|---------|
| System identity | "Nexus" or "we" | "I", "the system", "the AI", "your assistant" |
| Confidence | "Clear", "confirmed", "checked" | "We think", "probably", "it seems" |
| Trade-offs | "We traded", "chose X over Y" | "Unfortunately", "compromise", "sacrifice" |
| Failure | "Can't do that this weekend" | "Error", "failed", "unable to process" |
| Family | Use first names (Sarah, Emma, Jake) | "Your spouse", "family member 1", "the teenager" |
| Time | "25 min drive", "about 5 hours" | "Approximately 25 minutes", "ETA" |
| Approval | "Plan approved" | "Your plan has been successfully approved" |

### 10.3 Copy Length Rules

| Context | Max Length | Rationale |
|---------|-----------|-----------|
| Progress line | ~80 characters | One concise sentence, readable in < 2 seconds. Prioritize specificity over brevity when they conflict |
| Verdict strip | 3 phrases max | Scannable at a glance |
| "Why" section | 2–4 sentences per subsection | Enough to explain, short enough to read |
| Timeline event | Headline + 2 lines description | Scannable as a list |
| Checklist item | 1 line | Actionable, not explanatory |
| Error message | 1–2 sentences | State the problem + what to do |
| Sign-off | 1 sentence | Warm but not chatty |

---

## 11. Launcher Visual Design

### 11.1 Web Launcher Home Page (`/`)

The home page (`body.launcher`) is the primary entry point for the weekly ritual. It uses a full-screen centered layout — no columns, no sidebar.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                          System  Profile            │  ← .launcher-nav (top-right)
│                                                                     │
│                                                                     │
│                          Nexus                                      │  ← h1
│              Plan your weekend, locally.                            │  ← subtitle
│                                                                     │
│          ┌──────────────────────────────────────────┐               │
│          │  What are you planning this weekend?     │               │  ← #plan-form.launcher-form
│          │                                          │               │
│          │  ┌────────────────────────────────────┐  │               │
│          │  │ hike Sunday with the family       │  │               │
│          │  └────────────────────────────────────┘  │               │
│          │  [ Plan It → ]                           │               │
│          └──────────────────────────────────────────┘               │
│                                                                     │
│              Planning for Alex                                      │  ← identity line
│                                                                     │
│          Recent plans                                               │  ← recent plans list
│          Apr 12 — Las Trampas Wilderness ✔                          │
│          Apr 5  — Briones Loop ✔                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**CSS body class:** `launcher`

**Key elements:**

| Element | Selector | Purpose |
|---------|----------|---------|
| Top-right nav | `.launcher-nav` | System · Profile links |
| Main heading | `h1` | "Nexus" |
| Subtitle | `p.subtitle` | "Plan your weekend, locally." |
| Input form | `#plan-form.launcher-form` | Text input + "Plan It →" button |
| Identity line | `.identity-line` | "Planning for {name}" |
| Recent plans | `.recent-plans` | Scrollable list of past plans with status |

**Design notes:**
- No columns. Content stack is centered horizontally and vertically.
- Recent plans list is empty-state-safe: "No plans yet. Ready when you are."
- The form is the visual anchor. Everything else recedes.

### 11.2 CLI Launcher Output

The `nexus` CLI is a launcher only — it starts the web server and opens the browser. Terminal output is minimal.

When the user runs `nexus`:
```
  Nexus starting at http://localhost:7820
```
One line. Browser opens automatically. No further terminal output unless there's an error.

When the user runs `nexus plan "summit hike Sunday"`:
```
  Nexus starting at http://localhost:7820
  Planning: "summit hike Sunday"
```
Two lines. Browser opens with planning already started.

### 11.3 CLI Error Output

If the server can't start (port in use, Ollama not running):
```
  ✘ Ollama is not running — start it with: ollama serve
```
```
  ✘ Port 7820 is in use — try: nexus --port 7821
```

Errors use Rich formatting (red `✘`, green for suggested commands) but the terminal is not the primary interaction surface.

### 11.4 Color Palette (CLI only)

| Color | Usage | Rich Style |
|-------|-------|-----------|
| **Green** | Server URL, success | `[green]` |
| **Red** | Startup errors | `[red]` |
| **Dim** | Secondary info | `[dim]` |

---

## 12. Web Visual Design System

### 12.1 Design Constraints

The web UI is served locally by FastAPI with Jinja2 templates. All CSS is embedded — no CDN, no JavaScript frameworks. This ensures:
- Instant loading (localhost, no network requests)
- Offline viewing of saved plans
- Portability (Markdown exports work without internet)
- Privacy (no analytics, no external requests)

Plan HTML fragments use the same design tokens for inline rendering.

### 12.2 Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Page title | System sans-serif stack | 28px | 700 |
| Activity name | System sans-serif stack | 32px | 800 |
| Activity detail | System sans-serif stack | 18px | 400 |
| Stats bar | System sans-serif stack | 15px | 500 |
| Section heading | System sans-serif stack | 20px | 700 |
| Body text | System sans-serif stack | 16px | 400, line-height 1.6 |
| Timeline time | System monospace stack | 15px | 600 |
| Timeline text | System sans-serif stack | 15px | 400 |
| Button text | System sans-serif stack | 14px | 600, uppercase, letter-spacing 0.5px |
| Footer | System sans-serif stack | 13px | 400 |

**System font stack:**
```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
             "Helvetica Neue", Arial, sans-serif;
```

### 12.3 Color System

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#FFFFFF` | Page background |
| `--bg-card` | `#F8F9FA` | Card/section background |
| `--bg-verdict-ok` | `#E8F5E9` | Verdict strip — all clear |
| `--bg-verdict-warn` | `#FFF8E1` | Verdict strip — compromised |
| `--bg-verdict-fail` | `#FFEBEE` | Verdict strip — unsafe |
| `--text` | `#1A1A1A` | Primary body text |
| `--text-secondary` | `#5F6368` | Secondary text, descriptions |
| `--text-time` | `#37474F` | Timeline timestamps |
| `--accent` | `#1B5E20` | Buttons, links, emphasis |
| `--accent-hover` | `#2E7D32` | Button hover state |
| `--border` | `#E0E0E0` | Card borders, dividers |
| `--timeline-line` | `#BDBDBD` | Vertical timeline connector |
| `--reject-bg` | `#F5F5F5` | Reject button background |
| `--reject-text` | `#424242` | Reject button text |

**Dark mode:** Respects `prefers-color-scheme: dark`. The plan should look good on a phone at night or a dark-theme laptop.

| Token | Dark Value | Usage |
|-------|-----------|-------|
| `--bg` | `#121212` | Page background |
| `--bg-card` | `#1E1E1E` | Card/section background |
| `--bg-verdict-ok` | `#1B3A1B` | Verdict strip — all clear |
| `--bg-verdict-warn` | `#3A3520` | Verdict strip — compromised |
| `--bg-verdict-fail` | `#3A1B1B` | Verdict strip — unsafe |
| `--text` | `#E0E0E0` | Primary body text |
| `--text-secondary` | `#9E9E9E` | Secondary text, descriptions |
| `--text-time` | `#B0BEC5` | Timeline timestamps |
| `--accent` | `#66BB6A` | Buttons, links, emphasis |
| `--accent-hover` | `#81C784` | Button hover state |
| `--border` | `#333333` | Card borders, dividers |
| `--timeline-line` | `#555555` | Vertical timeline connector |
| `--reject-bg` | `#2A2A2A` | Reject button background |
| `--reject-text` | `#BDBDBD` | Reject button text |

### 12.4 Layout & Body Classes

The three pages use distinct CSS body classes:

| Page | Body class | Grid layout | Purpose |
|------|-----------|-------------|--------|
| Home (`/`) | `launcher` | None (flexbox centering) | Weekly entry point |
| Planning (`/plan?id=...`) | `cockpit` | `42% 1fr` (2 zones) | Live execution view |
| Plan (`/plans/{id}`) | `cockpit` (topbar/bottombar only) + `.plan-editorial` inner wrapper | None (single column) | Editorial reading view |

**Plan editorial column:**

| Property | Value |
|----------|-------|
| Max width | 720px |
| Horizontal padding | 24px (mobile: 16px) |
| Bottom padding | 80px (clears fixed bottombar) |
| Section spacing | 40px between major sections |
| Card padding | 24px |
| Card border-radius | 12px |
| Card border | 1px solid `--border` |
| Card shadow | `0 1px 3px rgba(0,0,0,0.08)` |

**Planning cockpit zones:**

| Zone | Selector | Width | Key children |
|------|----------|-------|-------------|
| Left | `.cockpit-left` | 42% | `#planning-graph` (SVG), `#inputs-context` |
| Right | `.cockpit-right` | 58% | `.context-hero#context-box`, `.agent-queue#agent-grid`, `.steer-section` |

**Responsive:** Plan editorial column is single-column, max-width centred. Cockpit zones stack vertically on viewports narrower than 800px.

### 12.5 Timeline Design

The timeline is a vertical line with time markers on the left and event descriptions on the right:

```css
.timeline {
  position: relative;
  padding-left: 48px;
}
.timeline::before {
  content: '';
  position: absolute;
  left: 20px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--timeline-line);
}
.timeline-event {
  position: relative;
  margin-bottom: 24px;
}
.timeline-event::before {
  content: '';
  position: absolute;
  left: -34px;
  top: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid white;
}
```

### 12.6 Button Design

Two action buttons at the bottom of the plan. Equal visual weight — approving and rejecting are equally valid choices.

```css
.btn {
  display: inline-block;
  padding: 14px 28px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
  border: none;
  transition: background 0.15s ease;
}
.btn-approve {
  background: var(--accent);
  color: white;
}
.btn-approve:hover {
  background: var(--accent-hover);
}
.btn-reject {
  background: var(--reject-bg);
  color: var(--reject-text);
  border: 1px solid var(--border);
}
.btn-reject:hover {
  background: #EEEEEE;
}
```

### 12.7 Print Styles

The plan should print cleanly (one page if possible):

```css
@media print {
  .decision-buttons { display: none; }
  .footer { display: none; }
  body { max-width: 100%; font-size: 12px; }
  .card { box-shadow: none; border: 1px solid #ccc; }
}
```

Users may want to print the itinerary for the car's glovebox or for a family member without a phone handy.

---

## 13. Error, Empty & Edge States

### 13.1 Error State Design Philosophy

Errors in Nexus fall into two categories:

1. **System errors** (Ollama not running, API key missing) — the system can't function
2. **Planning constraints** (no safe trails, rain all weekend) — the system functions but can't satisfy the request

Category 1 gets a clear diagnostic with fix instructions. Category 2 is not an error at all — it's the system doing its job (saying "no" when the answer is no).

### 13.2 Preflight Status Page (`/preflight`)

When prerequisites are not met, the browser shows a status page instead of the landing page. This replaces the old approach of individual error messages — the user sees everything at once and can fix issues in any order.

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820/preflight                                    │
│                                                              │
│  Getting Nexus ready                                         │
│  ───────────────────                                         │
│                                                              │
│  ✔ Python 3.12             ready                              │
│  ✔ Dependencies             synced                             │
│  ✘ Ollama                   not installed                      │
│    Install from: ollama.com/download                           │
│    [ Open Download Page ]                                     │
│  ○ Ollama server            waiting for install...             │
│  ○ Model qwen3.5:9b         waiting for install...             │
│  ✔ Disk space               47 GB free                         │
│  ✔ RAM                      36 GB                              │
│                                                              │
│  [ Re-check → ]                                              │
│                                                              │
│  ───────────────────                                         │
│  Tip: If you used start.command, these should be             │
│  handled automatically. You can close this tab and            │
│  double-click start.command again.                            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**After all checks pass (user clicks Re-check):**

```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820/preflight                                    │
│                                                              │
│  ✔ Everything looks good!                                     │
│                                                              │
│  ✔ Python 3.12             ready                              │
│  ✔ Dependencies             synced                             │
│  ✔ Ollama                   installed                          │
│  ✔ Ollama server            running                            │
│  ✔ Model qwen3.5:9b         ready                              │
│  ✔ Disk space               47 GB free                         │
│  ✔ RAM                      36 GB                              │
│                                                              │
│  Redirecting to Nexus...                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

*(Auto-redirects to `/` or `/setup` after 2 seconds.)*

**Preflight page design rules:**

| Rule | Rationale |
|------|-----------|
| Show all checks at once | User sees the full picture, not a drip-feed of errors |
| Gray out dependent checks | If Ollama isn't installed, "server" and "model" show as "○ waiting" — not failed |
| Fix actions are copy-paste or clickable | No asking the user to "figure out" how to install something |
| Re-check is non-destructive | Clicking Re-check re-runs all checks without restarting the server |
| Auto-redirect on success | Once all checks pass, the user is taken to Nexus automatically |
| Mention the launcher script | If the user got here by running `nexus` manually, remind them `start.command` handles this automatically |

### 13.3 System Error Messages

These appear when individual issues arise during normal operation (after preflight has passed). Each follows the three-part structure: **what happened → why → what to do.**

**Ollama not running:**
The browser redirects to `/preflight` showing the full status. If the user reaches this state outside of preflight (e.g., Ollama crashes mid-session), an inline banner appears:
```
  Nexus lost connection to Ollama.

  The local AI server may have stopped.

  Start it with:
    ollama serve

  Or double-click start.command — it handles this automatically.
  [ Re-check ]
```

**Model not installed:**
Handled by the `/preflight` page on startup. If detected mid-session (e.g., model was deleted):
```
  The model "qwen3.5:9b" is no longer available.

  Re-download it with:
    ollama pull qwen3.5:9b

  Or double-click start.command to fix automatically.
  [ Re-check ]
```

**No profile configured:**
```
  Redirecting to /setup — let's get you set up.
```
*(Handled automatically by redirecting to the setup page.)*

**API key missing (for required providers):**
```
  Yelp API key not found.

  Go to /setup → API Keys to add it,
  or add it manually to ~/.nexus/.env:
    YELP_API_KEY=your-key-here

  Get a free key at: https://www.yelp.com/developers
```

**Network error (external API unreachable):**
```
  Weather data unavailable — Open-Meteo isn't responding.

  Using cached forecast from 2 hours ago.
  Plan continues with slightly older weather data.
```
*(This is not a blocking error if cache exists — the system continues with annotation.)*

### 13.4 Planning Constraint Messages

These are not errors. They're the system being honest.

**No trails match criteria:**
The progress stream shows the failure and offers suggestions inline:
```
  ✘ No trails found matching 3,500+ ft within 90 min drive

  Try:
  • Lowering your elevation target
  • Increasing your driving range
  • "best hike within an hour, any elevation"
  [ Plan Again → ]
```

**All days have bad weather:**
```
  ✔ Found 4 options matching your preferences
  ✘ Saturday: heavy rain, 70% chance
  ✘ Sunday: AQI 115 — unhealthy for strenuous activity

  This weekend isn't safe for strenuous outdoor activities.
  Showing a modified plan below...
```

**Restaurant constraint impossible:**
```
  ✔ Great option at Black Diamond Mines
  ✘ No vegetarian restaurants within 10 miles of activity

  Trying options closer to town...
```

### 13.5 Empty States

**First run — no plans yet (landing page):**
```
┌──────────────────────────────────────────────────────────────┐
│  localhost:7820                                              │
│                                                              │
│  ┌──────────────────────────────────────────────┐            │
│  │  Nexus                                       │            │
│  │                                              │            │
│  │  No plans yet                                │            │
│  │  Ready when you are.                         │            │
│  │                                              │            │
│  └──────────────────────────────────────────────┘            │
│                                                              │
│  What are you planning this weekend?                         │
│  ┌──────────────────────────────────────────────────┐        │
│  │                                                  │        │
│  └──────────────────────────────────────────────────┘        │
│  [ Plan It → ]                                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**No pending plan (landing page):**
The pending plan card simply doesn't appear. The landing page shows recent history and the planning input.

**No recent plan for feedback:**
The "How did it go?" link doesn't appear on plans that already have feedback. If there are no completed plans, the plan history page shows: "No trips to reflect on yet — go have an adventure first."

### 13.6 Edge Case: Stale Cache & Confidence Labels

The plan footer always shows data confidence for key data sources using the `DataConfidence` labels from Tech Spec §6.6:

**Normal operation (all live data):**
```
  Nexus · Generated Apr 18, 2026 at 8:14 PM
  Weather: verified (12 min) · Route: verified · Cell: estimated
```

**Stale cache (API was unavailable):**
```
  Nexus · Generated Apr 18, 2026 at 8:14 PM
  Weather: cached (4 hours — refresh recommended) · Route: verified · Cell: estimated
```

**Mixed confidence with incomplete restaurant data:**
```
  Nexus · Generated Apr 18, 2026 at 8:14 PM
  Weather: verified · Route: estimated (routing service unavailable) · Dietary: could not verify
```

**Footer label rules:**
- `verified` — plain text, no special styling
- `cached` — show age; if age > freshness window, add "(refresh recommended)"
- `estimated` — show always, no age (heuristics don't have freshness)
- Cell coverage is **always** `estimated` until a real coverage API is added (post-MVP)
- Dietary compliance is `estimated` with "could not verify" when Yelp menu data is incomplete

This replaces the previous plain "Weather data: 12 min old" format with structured confidence labels that match the PRD's Explainable Output Contract (§9.4).

---

## 14. Accessibility

### 14.1 Launcher Terminal Accessibility

| Concern | Design Response |
|---------|----------------|
| Color blindness | Icons (✔, ✘) carry meaning independently of color |
| Screen readers | All text is plain text — no graphical elements in terminal |
| High-contrast terminals | Color palette uses distinct hue values, not just lightness |

### 14.2 Web UI Accessibility

| Concern | Design Response |
|---------|----------------|
| Semantic HTML | Proper heading hierarchy (h1 → h2 → h3), landmark roles |
| Keyboard navigation | All interactive elements (buttons, text input) focusable via Tab |
| Focus styles | Visible focus ring on buttons and inputs (not suppressed) |
| Alt text | Decorative elements use `aria-hidden`; meaningful images get alt text |
| ARIA labels | Buttons include `aria-label` for screen readers |
| Reduced motion | `prefers-reduced-motion` disables any transitions |
| Text sizing | All text in `rem`/`em`, no `px` for body text |
| Contrast ratios | All text passes WCAG AA (4.5:1 minimum) |
| Dark mode | Full dark mode support via `prefers-color-scheme: dark` |
| Print | Decision buttons hidden; plan prints clean on one page |

### 14.3 Inclusive Copy

- Family relationships are never assumed: "Sarah" not "your wife"
- Fitness levels are described by capability, not judgment: "Advanced — seeking elevation and distance challenges" not "Advanced — for experienced hikers only"
- Dietary restrictions are stated factually, never qualified: "Vegetarian" not "Vegetarian (limited options)"

---

## 15. UX Metrics & Validation

### 15.1 Core UX Metrics

These metrics measure whether the UX is achieving its goals. They complement the product metrics in PRD §12.1.

| Metric | Target | How to Measure | Why It Matters |
|--------|--------|---------------|----------------|
| **Time to first plan** | < 12 min (clone → approved plan) | Timed user test | First-use friction kills adoption |
| **Setup completion rate** | > 95% | Completion of setup wizard vs. abandonment | Setup friction kills before first value |
| **Approval time** | < 3 min (plan appears → decision) | Time between plan render and approve/reject | Plan readability and trust |
| **Rejection feedback length** | 5–20 words average | Word count of rejection text | Too short = unclear; too long = system asked too much |
| **Feedback completion rate** | > 60% of approved plans | Feedback submissions / approved plans | Habit loop closure |
| **Weekly retention** | 3 of 4 weeks | Usage log timestamps | Habit formation |
| **Repeat rejection rate** | < 25% | Plans rejected twice or more / total plans | System learning effectiveness |

### 15.2 UX Validation Approach

**Phase 1 — Dogfooding (Weeks 1–4):**
The author uses Nexus for 4 consecutive weekends of real planning. Every friction point, confusing message, or moment of "I'd rather just do this manually" is logged.

**Phase 2 — Family validation (Weeks 5–8):**
Spouse reviews HTML plans and provides honest "would you trust this?" feedback. Teenagers react to family activity suggestions.

**Phase 3 — First external user (Weeks 9–12):**
One trusted technical friend installs from README, runs `nexus`, and generates their first plan. No guidance provided. Every question they ask reveals a UX gap.

### 15.3 UX Red Flags

If any of these occur, the UX needs redesign in that area:

| Red Flag | Indicates |
|----------|-----------|
| User reads plan and opens a weather app to double-check | Trust failure — plan doesn't convey confidence |
| User asks "which trail should I pick?" | System presented options instead of a recommendation |
| User types `nexus` and then looks up command-line flags | Launcher isn't intuitive enough |
| User double-clicks `start.command` and nothing visible happens | Launcher feedback is insufficient |
| User sees `/preflight` page and doesn't know what to do | Preflight fix instructions are unclear |
| User skips feedback form consistently | Feedback flow is too long or feels pointless |
| User modifies the Markdown plan manually before executing | Plan output is missing details they need |
| User says "I don't trust it" after first use | Progress display doesn't show enough work being done |
| Spouse says "this looks like a computer made it" | Narration tone is too clinical |

---

*End of UX Specification*
