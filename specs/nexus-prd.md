# Product Requirements Document: Project Nexus

> **Version:** 1.6.0-draft  
> **Status:** Draft - Incorporating Review Feedback  
> **Author:** Ved  
> **Last Updated:** 2026-04-18

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Goals & Learning Objectives](#2-project-goals--learning-objectives)
3. [Target Persona & Use Case](#3-target-persona--use-case)
4. [Problem Statement](#4-problem-statement)
5. [Solution Overview](#5-solution-overview)
6. [System Behavior](#6-system-behavior)
7. [Data the System Manages](#7-data-the-system-manages)
8. [Core Features](#8-core-features)
9. [User Experience](#9-user-experience)
10. [Non-Functional Requirements](#10-non-functional-requirements)
11. [External Integrations & APIs](#11-external-integrations--apis)
12. [Success Metrics](#12-success-metrics)
13. [Scope & Boundaries](#13-scope--boundaries)
14. [Open Questions](#14-open-questions)
15. [Glossary](#15-glossary)

---

## 1. Executive Summary

**Nexus gives busy parents one trustworthy weekend plan that balances one person's training goal with everyone else's day—without sending family data to the cloud.**

The typical Saturday morning negotiation—cross-referencing weather apps, trail databases, restaurant menus, and four people's preferences—takes 90+ minutes of cognitive labor that could be spent living the weekend instead of planning it. Nexus eliminates that tax: submit a single natural-language request, and the system delivers a recommended plan with a backup option and a plain-English explanation of why each decision was made. The user's only job is to say yes or no.

**What makes Nexus different from asking an LLM:**
- Plans are validated against real conditions (live weather, recent trail reports, actual restaurant menus), not generated from training data
- Every constraint—the teenager's need for cell service, the vegetarian recovery meal, the elevation target—is verified automatically, every time
- If no perfect plan exists, the system still recommends the best available compromise with transparent trade-offs
- All LLM inference and all family data stays on the local machine

**What this project also is:** An open-source demonstration of multi-agent system design using LangGraph—built to be readable, forkable, and educational. The architecture intentionally surfaces each design pattern so other engineers can learn from and extend it. Both goals are explicit and compatible: a genuinely useful product that is also an excellent learning artifact.

---

## 2. Project Goals & Learning Objectives

### 2.1 Primary Project Goals

> **Dual-Purpose Declaration:** Nexus is explicitly both a useful product and an engineering showcase. These goals are named here to avoid the distortion that comes from mixing them silently. Product decisions optimize for user value; showcase decisions optimize for code clarity and educational signal. When they conflict, product value wins.
>
> **Critical boundary:** The showcase goal is expressed entirely through code quality—readable architecture, explanatory comments, clear LangGraph patterns in the repository. It is **never** expressed through the user-facing interface. The product must feel like one smart assistant, not a "multi-agent swarm." LangGraph should be invisible to the user.

| Goal | Type | Description | Success Indicator |
|------|------|-------------|-------------------|
| **Trustworthy Planning** | Product | Deliver one reliable plan a busy parent can act on immediately | > 70% first-pass approval; zero hard-constraint violations |
| **Practical Utility** | Product | Solve a genuine problem the author faces weekly | Used for actual weekend planning, not just demo runs |
| **LangGraph Mastery** | Showcase | Demonstrate cyclical execution, state management, and conditional routing | Code is self-explanatory to a LangGraph newcomer |
| **Community Contribution** | Showcase | Inspire others to build multi-agent systems | Forks, PRs, and derivative projects |

### 2.2 LangGraph Learning Objectives

By completing this project, demonstrate mastery of:

1. **Graph Construction**
   - Defining nodes (agents) and edges (transitions)
   - Conditional routing based on state
   - Cyclical graph patterns (loops with exit conditions)

2. **State Management**
   - Designing typed state schemas with Pydantic
   - State reducers for merging agent outputs
   - Checkpoint persistence and recovery

3. **Agent Coordination Patterns**
   - Supervisor/worker topology
   - Adversarial review (agents that reject proposals)
   - Consensus detection and loop termination

4. **Human-in-the-Loop**
   - Interrupt points for human review
   - Feedback incorporation and re-routing
   - Notification and approval workflows

5. **Tool Integration**
   - Binding external APIs to agent capabilities
   - Managing tool call failures gracefully
   - Caching and rate limiting for external services

### 2.3 Stretch Goals

- [ ] Multi-model orchestration (different LLMs for different agents based on task)
- [ ] Voice interface for hands-free plan review
- [ ] Calendar integration for automatic availability detection
- [ ] Mobile companion app (native) for on-the-go plan access

---

## 3. Target Persona & Use Case

### 3.1 Primary Persona: "The High-Bandwidth Professional"

**Name:** Alex (composite persona)

**Demographics:**
- Age: 40-50
- Occupation: Senior technical professional (engineer, architect, executive)
- Family: Married with 2 children (ages 12 and 17)
- Location: Suburban area within 2 hours of outdoor recreation (mountains, coast, parks, trails)

**Psychographics:**

| Dimension | Characteristic |
|-----------|----------------|
| **Time Scarcity** | Weekends are the only window for meaningful family time and personal fitness |
| **Optimization Mindset** | Seeks maximum value from limited time; dislikes inefficiency |
| **Technical Literacy** | Comfortable with terminal, local servers, and configuration files |
| **Privacy Consciousness** | Distrusts cloud services with family location/schedule data |
| **Physical Goals** | Trains for endurance events; needs specific elevation gain and intensity |
| **Dietary Constraints** | Strict nutritional requirements tied to athletic performance |

**Family Dynamics:**

| Member | Age | Interests | Constraints |
|--------|-----|-----------|-------------|
| Spouse | 42 | Reading, cafes, moderate walking | Max 2-3 miles outdoor distance, needs connectivity |
| Teen 1 | 17 | Photography, music, social media | Needs WiFi/cell service, hates repetitive activities |
| Teen 2 | 12 | Video games, swimming, adventure | Easily bored, needs engaging activities |

### 3.2 Use Case Scenarios

**Scenario 1: The Classic Weekend Dilemma**
> "I want to do a hard summit push on Saturday—ideally 3,500+ ft elevation gain. But my wife wants to visit that new bookstore cafe, my 17-year-old will revolt if there's no cell service, and my 12-year-old needs something active to do. Oh, and I need a high-protein vegetarian meal after. Make it work."

**Scenario 2: Weather-Dependent Pivot**
> "I had planned to hike Mt. Diablo this Sunday, but I just saw there might be rain. Find me an alternative with similar stats that works for everyone, or tell me if Sunday is salvageable."

**Scenario 3: Opportunistic Planning**
> "We have an unexpectedly free Saturday. What's the best option given current conditions?"

**Scenario 4: Non-Hiking Activity**
> "Let's do a beach day this weekend — the kids want to swim, I'd love a coastal bike ride, and Sarah wants a cafe with an ocean view. Something within an hour's drive."

**Scenario 5: Mixed Activity Day**
> "Plan a Saturday in the city — farmers market in the morning, a park for the kids, and a good lunch spot. Nothing too strenuous."

---

## 4. Problem Statement

### 4.1 The Core Problem

**Multi-variable constraint satisfaction with incomplete information and conflicting objectives.**

Planning a family weekend that satisfies everyone requires simultaneously optimizing across:

- **Temporal constraints:** Available time windows, travel time, activity duration
- **Spatial constraints:** Distance limits, location clustering, parking availability  
- **Environmental constraints:** Weather, trail conditions, seasonal factors
- **Individual preferences:** Divergent interests across 4+ family members
- **Physical constraints:** Fitness levels, dietary needs, accessibility requirements
- **Economic constraints:** Budget for meals, activities, gas

### 4.2 Why Current Solutions Fail

| Solution | Failure Mode |
|----------|--------------|
| **Single LLM Prompt** | "Lazy compliance"—generates plausible but untested plans that break on first constraint check |
| **Manual Research** | Cognitive overload; user must cross-reference 5+ data sources (weather, trails, restaurants, maps, calendars) |
| **Trip Planning Apps** | Optimized for tourists, not locals; ignore fitness metrics and dietary constraints |
| **Family Discussion** | Devolves into negotiation fatigue; loudest voice wins, not optimal solution |

### 4.3 The Mental Load Tax

Current workflow for the target persona:

1. Check weather forecast (5 min)
2. Browse activity sites — AllTrails, Yelp, local event calendars (15 min)
3. Cross-reference with conditions and reviews (10 min)
4. Search for nearby activities for kids (15 min)
5. Find restaurants with suitable menu options (20 min)
6. Propose to family, receive objections (10 min)
7. Repeat steps 2-6 with adjustments (30+ min)

**Total: 90+ minutes of cognitive labor, often repeated weekly.**

---

## 5. Solution Overview

### 5.1 The Nexus Approach

Nexus replaces user-driven research with **autonomous agent negotiation**, surfaced through a local web interface where the user can watch progress, inject constraints, and approve or redirect — all in one browser tab:

```
Browser UI → Agent Negotiation → Live Progress → Collaborative Review → Human Approval
      ↑                                ↓               ↓
      └──── Mid-Planning Input ────────┘               │
      └──── Rejection Feedback ────────────────────────┘
```

**Key Innovations:**

1. **Agents as Advocates:** Each agent represents a stakeholder or constraint domain, arguing for their requirements
2. **Adversarial Validation:** Agents actively reject proposals that violate their constraints
3. **Cyclical Resolution:** The graph loops until all agents reach consensus or max iterations
4. **Transparent Negotiation:** Users see *why* decisions were made, not just the final plan
5. **Collaborative Planning:** Users can inject constraints mid-planning, redirect the system before it finishes, or interrupt and refine — not just approve/reject a finished output

### 5.2 Value Proposition

| For User | For Community |
|----------|---------------|
| Reduce planning time from 90+ min to 5 min review | Reference implementation of multi-agent patterns |
| Ensure constraints are never forgotten | Documented LangGraph best practices |
| Discover options they wouldn't have found manually | Extensible architecture for other domains |
| Maintain privacy with local-first LLM inference | Privacy-conscious AI system design |

### 5.3 Constraint Hierarchy

The system must classify constraints explicitly to resolve conflicts between agents and avoid the contradiction between "all hard constraints must be met" and "graceful degradation when an agent cannot obtain data."

**Hard Constraints — never violated; plan is discarded or flagged if breached:**
- Safety: dangerous weather (lightning, extreme heat, wildfire smoke), official closures (trails, beaches, parks), insufficient daylight for planned duration
- Timing impossibility: activity overlaps, total driving time exceeds user-defined hard cap
- Dietary: absolute restrictions (vegetarian, food allergens)
- Connectivity: teenager present with zero cell service at any point during wait period

**Soft Constraints — best-effort; noted in plan summary when unmet:**
- Fitness target: preferred elevation gain and distance (can be partially satisfied; % of goal reported)
- Meal proximity: preferred distance to a compliant restaurant from activity location
- Family activity quality: preferred activities vs. acceptable minimums (e.g., specific venue vs. any town with cell service)
- Activity novelty: preference for activities/locations not recently visited by the user

**Tie-Break Rules — when multiple plans satisfy all hard constraints:**
1. Highest weather confidence score
2. Closest match to primary fitness target (elevation gain % of goal)
3. Highest composite family satisfaction score (ratio of soft constraints met across all family members)
4. Least total driving time

**Constraint Conflict Resolution Priority:** When hard constraints from different domains conflict (e.g., the only safe-weather day has no dietary-compliant restaurant), the system resolves using this fixed priority:
1. **Safety** — always wins; unsafe plans are never presented
2. **Timing** — impossible overlaps cannot be negotiated
3. **Dietary** — absolute restrictions are non-negotiable
4. **Connectivity** — cell service for teenagers is a family-safety proxy
5. **Fitness target** — first soft constraint to be relaxed
6. **Proximity / convenience** — most flexible

If top-priority constraints eliminate all options, the system reports "no safe plan" rather than silently violating a hard constraint.

**Compromise Definition:** When no plan satisfies all constraints, the system may present a "best compromise." **Compromise means relaxing soft constraints only — hard constraints are never violated.** The plan output must explicitly state which soft constraints were relaxed and by how much. If hard constraints cannot be satisfied, the system halts with "no safe plan" — it never downgrades a hard constraint to soft to force a result.

**Graceful Degradation Rule:** If an external API is unavailable, components operating on that data use cached values and annotate the output with data age and a confidence label (`verified` / `cached` / `estimated`). A component governing a hard constraint domain with no data at all (live or cached) halts planning rather than proceeding silently. A component governing only soft constraints may substitute a conservative default assumption, labeled `estimated` in the plan output.

---

## 6. System Behavior

### 6.1 How the System Works (Product View)

Nexus processes a planning request through four product-facing stages. The user perceives a single assistant doing thorough research; internally, specialized components handle each constraint domain independently.

**Stage 1 — Intent Understanding:**
The system parses the user's natural-language request into structured planning requirements: target date, fitness goals, dietary needs, family constraints.

**Stage 2 — Candidate Discovery:**
The system searches for activities matching the user's goals (fitness criteria, interests, family needs) within the configured driving range.

**Stage 3 — Constraint Validation:**
Each proposed plan is evaluated against five independent constraint domains, running in parallel:

| Constraint Domain | What It Checks | Hard/Soft |
|-------------------|---------------|-----------|
| **Weather & Environment** | Precipitation, AQI, lightning, conditions, daylight | Hard |
| **Family Needs** | Cell service for teenagers, activities near activity location, engagement for all members | Hard (cell service), Soft (activity quality) |
| **Dining** | Dietary-compliant restaurant within range, protein/macro targets | Hard (dietary compliance), Soft (proximity, variety) |
| **Logistics** | Total driving time, timeline conflicts, parking | Hard (driving cap, overlap), Soft (preference) |
| **Safety** | Composite risk assessment, emergency services proximity, route communication | Hard (absolute veto) |

If any hard constraint is violated, the system automatically revises the proposal — trying a different day, activity, or configuration — and re-validates. This loop repeats until all hard constraints are met or the system determines no safe plan is possible (maximum 3 internal iterations).

**Stage 4 — Plan Presentation:**
Once a plan passes all validations, the system generates a human-readable itinerary and presents it for approval.

### 6.2 Execution Flow

```
  User Intent
       │
       ▼
  Parse Requirements
       │
       ▼
  ┌─ Discover Candidates ◄────────────────────┐
  │         │                                  │
  │         ▼                                  │
  │  Validate Constraints (parallel)           │
  │  [Weather · Family · Dining ·              │
  │   Logistics · Safety]                      │
  │         │                                  │
  │    ┌────┴────┐                             │
  │    │         │                             │
  │  Pass      Fail ──── Revise & Retry ───────┘
  │    │         
  │    ▼         
  │  Present Plan to User                
  │    │                                 
  │  ┌─┴──┐                             
  │  │    │                              
  │ Yes   No + Feedback ──── Replan ─────┘
  │  │
  │  ▼
  └─ Save Plan (HTML + Markdown)
```

### 6.3 Consensus & Termination Rules

| Condition | System Behavior |
|-----------|----------------|
| All constraint domains pass | Proceed to human review |
| Any hard constraint fails | Revise proposal automatically and re-validate |
| Constraint domain cannot evaluate (missing data, no cache) | Halt planning and explain what's blocking — never guess on hard constraints |
| Constraint domain has only soft failures | Proceed, note unmet soft constraints in plan output |
| Maximum iterations reached without full consensus | Present best-compromise plan with unresolved soft conflicts noted |
| Critical safety failure (no safe option exists) | Terminate planning; present "no safe plan" with blocking reason and earliest safe window |
| User rejects with feedback | Incorporate feedback as new constraint, restart validation loop |

### 6.4 Human Rejection Loop Rules

| Condition | System Behavior |
|-----------|----------------|
| User rejects with feedback | Replan with feedback injected as a new constraint |
| User rejects with identical feedback twice | Offer "Go with this plan anyway?" or suggest manual planning |
| User rejects 5 times in one session | Suggest manual planning: "This one might need a human touch — try adjusting your constraints or planning manually this week" |
| User rejects with no feedback | Prompt for at least a brief description of what to change |

### 6.5 Unified Termination Policy

All iteration and retry limits across the system are governed by a single policy to prevent competing termination systems. This is the canonical source of truth — referenced by the [Technical Specification](nexus-tech-spec.md) and [UX Specification](nexus-ux-spec.md).

| Loop Type | Limit | Behavior at Limit |
|-----------|-------|-------------------|
| **Internal consensus loop** | 3 iterations | Present best-compromise plan (soft constraints relaxed, hard constraints satisfied) with unresolved conflicts noted |
| **Human rejection loop** | 2 identical rejections | Offer "go with this plan anyway?" — the system has exhausted its revision space for that feedback direction |
| **Human rejection loop** | 5 total rejections (any feedback) | Suggest manual planning: "This one might need a human touch." Stop replanning. |
| **Per-node LLM timeout** | 15 seconds | Hard-constraint agents: REJECTED verdict (cannot proceed without data). Soft-constraint agents: NEEDS_INFO verdict; graph continues without that agent's approval |
| **Total planning time cap** | 90 seconds | Force current best proposal to safety review, then present to user with "planning time exceeded" annotation |
| **API call retry** | 3 attempts with exponential backoff | Fall back to cache (soft) or halt (hard constraint domain) |

**Precedence:** Safety termination (critical failure → no safe plan) overrides all other limits. The total planning time cap overrides the internal consensus loop. The human rejection limit is independent of internal loops — each rejection triggers a fresh internal consensus run (up to its own limit).

---

## 7. Data the System Manages

The system stores and processes three categories of data. All data resides locally — nothing is synced to the cloud.

**User & Family Profiles (persistent, user-configured):**
- User's fitness level, dietary restrictions, protein targets, home location, driving limits
- Each family member's name, age, interests, outdoor comfort distance, cell service requirements

**Planning State (transient, per-request):**
- The current activity proposal, family activity assignments, and restaurant recommendation
- Constraint validation results from each domain
- Revision history (what was tried and why it was rejected)
- The plan is checkpointed at each stage, enabling pause/resume if the process is interrupted

**Plan Archive (permanent, user-managed):**
- Approved plans saved as Markdown files for personal knowledge management (Obsidian sync)
- Post-trip feedback entries stored locally
- Debug logs (opt-in via `--debug` flag) for troubleshooting

> **Technical implementation:** Data schemas, state management patterns, and checkpoint persistence are specified in the [Technical Specification](nexus-tech-spec.md) §6.

---

## 8. Core Features

### 8.1 MVP Features (v1.0)

The MVP is narrowed to one magical workflow: **one request → one recommended plan → one backup option → approve or reject.** Features are cut to protect the first-use experience; the full six-agent story remains internal architecture, not exposed surface area.

| ID | Feature | Description | Priority |
|----|---------|-------------|----------|
| F1 | **Natural Language Intent** | Accept freeform planning requests via CLI | P0 |
| F2 | **Activity Discovery** | Search and rank activities matching fitness criteria and family interests | P0 |
| F3 | **Weather Validation** | Validate safety and suitability against live forecast | P0 |
| F4 | **Family Anchor Check** | Verify cell service and an acceptable waiting spot near activity location | P0 |
| F5 | **Meal Proximity Check** | Confirm a dietary-compliant restaurant exists within drive range | P0 |
| F6 | **Cyclical Resolution** | Auto-revise when hard constraints are violated | P0 |
| F7 | **Human-in-the-Loop Review** | Surface plan for a single approve/reject decision | P0 |
| F8 | **Human-Centric Plan Summary** | Output explains in plain English why this plan was chosen and what was checked — no agent names, no confidence percentages, no iteration counts | P0 |
| F9 | **Backup Plan** | Always include one backup option alongside the recommended plan | P0 |
| F10 | **Best-Compromise Output** | When no perfect plan exists, system selects the best compromise and presents one confident recommendation — not a menu of options | P0 |
| F11 | **Local Web UI** | Single-browser-tab experience: input, live progress with mid-planning constraint injection, inline plan rendering, approve/reject, feedback — all at `localhost`, no cloud | P0 |
| F12 | **Local-First LLM Inference** | All LLM calls run locally via Ollama; no family data leaves the machine | P0 |
| F17 | **Post-Trip Feedback** | Feedback form on the plan page after the weekend; prompts user to record what worked, what didn't, and any real-world failures (closed trail, wrong restaurant hours); stored locally to improve future plans | P0 |
| F18 | **Browser-Based API Key Setup** | API keys for required providers (Yelp) configured through the `/setup` flow — not manual `.env` editing; keys are saved to `.env` on disk and never displayed after entry. Hiking Project key is optional (enhances trail data but Overpass covers all activity types without a key) | P0 |
| F19 | **Zero-Friction Launcher** | Double-clickable `start.command` (macOS) / `start.sh` (Linux) script that checks all prerequisites, installs missing components (uv, Ollama, model), and launches Nexus — no manual terminal commands required | P0 |
| F20 | **Startup Preflight Check** | On every launch, Nexus validates all prerequisites (Ollama running, model available, disk space, port) and shows a browser-based status page with one-click fixes for any failures — not raw terminal errors | P0 |
| F13 | **Full Nutritional Macro Optimization** | Calculate precise protein/macro targets and verify against specific menu items | P1 |
| F14 | **Full Family Activity Matching** | Find and rank specific activities for each family member individually | P1 |
| F15 | **Debug Log** | Internal round-by-round decision log written to file and accessible via `--debug` flag; never surfaced in default user output | P1 |
| F16 | **Guided First-Run Setup** | Browser-based onboarding flow to build family profile with forms, validation, and inline editing — no YAML required | P0 |

### 8.2 Post-MVP Features (v1.x)

> **Gate:** None of these features will be designed or scoped until the core v1.0 loop (§8.1) has been proven through at least 4 consecutive weekends of real-world use with a first-pass approval rate ≥ 70% and a real-world failure rate ≤ 5%. A good plan that consistently works is the prerequisite for everything else.

| ID | Feature | Description | Priority |
|----|---------|-------------|----------|
| F21 | Calendar Integration | Auto-detect availability from calendar | P1 |
| F22 | Historical Learning | Improve recommendations based on past approvals and post-trip feedback | P1 |
| F23 | Voice Interface | Hands-free plan review via speech | P2 |
| F24 | Multi-Day Planning | Extend to weekend trips with lodging | P2 |
| F25 | Social Sharing | Generate shareable trip summaries | P3 |

### 8.3 The Negotiation Log (Debug-Only)

The internal decision log records every agent verdict, rejection reason, and iteration in detail. It is a **developer tool, not a user feature.**

**Default behavior:** Never shown. The user sees only the final plan and its plain-English rationale.

**Access:** `nexus plan "..." --debug` writes the full log to `~/.nexus/logs/` and prints a summary to the terminal.

**Rationale:** Showing users a transcript of internal system decisions—agent names, iteration counts, "Nutritional Gatekeeper approved"—breaks the experience. Trust comes from the plan working when they execute it, not from validating the system's homework. The log exists for debugging failed plans and for developers studying the LangGraph implementation.

---

## 9. User Experience

### 9.1 Interaction Model

Nexus uses a **single browser tab** as the entire interaction surface. The user types a request, watches live progress, can inject constraints mid-planning, and approves or rejects the plan — all without switching contexts.

**Core flow:**
1. **Launch:** `nexus` opens a browser tab at `localhost`. (Or `nexus plan "..."` opens with planning already started.)
2. **Submit Intent:** Type a natural-language request in the browser input field
3. **Live Progress:** Constraint checks stream in real-time. An input field is always available to add constraints mid-planning ("actually, Emma has soccer at 2pm")
4. **Plan Appears:** Fully verified itinerary renders inline in the same page — no page switch, no separate file
5. **Decision:** Approve (plan saved) or reject with one sentence of feedback (system replans) — buttons and input are native in the page
6. **On Approve:** Markdown version saved to `~/.nexus/plans/` for Obsidian sync

**Why a browser, not a terminal:** The system already generates HTML for plan output. A terminal entry point forces cross-surface interaction (terminal → browser → terminal) with workarounds for approve/reject. A local web UI eliminates this split and enables mid-planning interruption, which a terminal cannot support. The server is `localhost`-only — no network exposure, no cloud, no authentication.

### 9.2 UX Requirements

| Requirement | Specification |
|-------------|---------------|
| **Single interaction surface** | Everything happens in one browser tab — input, progress, plan, decision, feedback. No terminal ↔ browser switching |
| **Mid-planning input** | The user can add constraints while planning is in progress ("Emma has soccer at 2"). The system incorporates the constraint without restarting from scratch |
| **Visible progress** | Each constraint check appears as a live status update with the result — the user sees work being done on their behalf, not a generic wait indicator |
| **Plan as itinerary** | Output is a beautifully formatted itinerary rendered inline in the browser page. It reads like a premium travel itinerary, not a data dump |
| **No system internals exposed** | The user never sees agent names, confidence scores, iteration counts, or architecture terms. If any of these leak into the user-facing output, that is a bug |
| **One recommendation** | The system presents one plan with one backup — not a menu of options. The user's role is to approve or redirect, not to analyze and compare |
| **Effortless rejection** | Rejecting a plan requires only one sentence of natural-language feedback typed inline — no forms, no IDs, no structured input |
| **Transparent trade-offs** | When a plan can't meet all goals, the output states plainly what was sacrificed and why, with specific numbers |
| **Data confidence visible** | Plan output distinguishes `verified` (live data), `cached` (stale but usable), and `estimated` (heuristic/proxy) data — so users know what to trust. Cell coverage is always labeled `estimated`. |
| **Honest when no plan works** | The system says "no" when the answer is no (unsafe weather, irreconcilable constraints), offers a downscaled alternative, and suggests trying next weekend |
| **Family-accessible** | Spouse or family member can open the same `localhost` URL on their phone to view the plan — no technical skills required |

### 9.3 Input Interfaces (MVP)

| Interface | Description | Use Case |
|-----------|-------------|----------|
| **Browser UI** | Text input at `localhost` — type natural-language request | Primary planning interface |
| **CLI Shortcut** | `nexus plan "beach day Sunday"` — opens browser with planning already started | Terminal power-user convenience |
| **Browser Setup** | `/setup` page — guided first-run profile builder with forms | Onboarding; no YAML editing required |
| **YAML Profile** | `~/.nexus/profile.yaml` — advanced import/export path | Power users, version control, backup |

> **Onboarding Note:** YAML is the persistence format, not the setup interface. The primary first-run experience is: double-click `start.command` → prerequisites auto-install → browser opens → guided profile setup. The user never touches a terminal unless they choose to. A repeated weekly product lives or dies on first-use friction.

### 9.4 Explainable Output Contract

The PRD commits to "transparent negotiation" (§5.1) while the UX hides all system internals. These are not contradictory — they define a precise boundary:

**Users see:**
- Why this day/time was chosen (weather comparison, scheduling conflicts avoided)
- What constraints were satisfied and which trade-offs were made (with specific numbers)
- What data sources informed the plan (weather, restaurant hours, conditions)
- Data confidence for each claim (`verified` / `cached` / `estimated`)

**Users do NOT see:**
- Agent names or identities (MeteorologyAgent, FamilyCoordinator, etc.)
- Validation topology or graph structure
- Iteration count or consensus loop details
- Confidence percentages or internal scoring
- Which constraints were checked by deterministic code vs. LLM

This contract is the canonical reference for any implementation decision about what appears in user-facing output. If a UI element cannot be classified into one of the two lists above, it defaults to "do NOT see."

### 9.5 Output Artifacts

| Artifact | Format | Purpose | Lifecycle |
|----------|--------|---------|-----------|
| **Plan Itinerary** | Web page at `localhost` | Beautiful, immediately actionable plan rendered inline after planning completes | Visible in the same browser tab; persists until next plan |
| **Plan Archive** | Markdown | Obsidian-compatible file for personal knowledge management | Saved on approval to `~/.nexus/plans/` |
| **Plan History** | Web page at `/plans` | Browsable history of past plans with feedback status | Always available while server is running |
| **Debug Log** | Text file | Internal decision log for troubleshooting (developer-only) | Written to `~/.nexus/logs/` with `--debug` flag |

### 9.5 Plan Content Requirements

Every approved plan output must include:

1. **Activity name and key stats** (type, location, distance/duration, difficulty if applicable, departure time) — scannable in 5 seconds
2. **Verified conditions verdict** ("Forecast clear. Conditions good. Table confirmed.") — specific claims, not vague assurances
3. **Why this plan** — 2–4 sentences explaining the day/time choice and what was avoided
4. **Trade-off disclosure** — what was sacrificed and why, with specific numbers (e.g., "89% of your elevation goal")
5. **Full-day timeline** — from departure to return, naming each family member and their activities
6. **Backup option** — one alternative activity with key stats, ready if conditions change
7. **Preparation checklist** — gear, water, device charging, restaurant hours
8. **Emergency info** — nearest hospital, ranger station, cell service status at key points
9. **Decision buttons** — approve and reject actions with equal visual weight

> **Design details:** Wireframes, visual hierarchy, copy rules, and styling are specified in the [UX Specification](nexus-ux-spec.md) §6.

---

## 10. Non-Functional Requirements

### 10.1 Privacy & Security

The "local-first" claim requires precision: LLM inference is fully local; external data queries are not, but are mitigated by provider selection, input sanitization, and aggressive caching.

| Requirement | Specification | Privacy Level |
|-------------|---------------|---------------|
| **Local LLM Inference** | All reasoning runs via Ollama on local hardware by default; no prompts or family data sent to cloud AI providers. Users may opt in to cloud models for non-PII agents (e.g., activity ranking, plan narration) via config — Family Coordinator is always local. See Tech Spec §3.2 | Fully local (default) |
| **External Data Queries** | Weather, activity/trail, and restaurant lookups require network requests; area names or coordinates are transmitted to the chosen provider | Network — mitigated |
| **Privacy-Ranked API Selection** | Default providers chosen for minimal data exposure (Open-Meteo requires no API key; NWS is US gov); home address is never used as an API input — only destination area names or nearest town | Mitigated |
| **Data Residency** | All profiles, plans, and logs stored in local SQLite; never synced to cloud | Fully local |
| **No Telemetry** | Zero analytics or usage tracking by default | Fully local |
| **Credential Isolation** | API keys stored in local `.env`; configured via browser-based setup page or manual file editing; never logged or transmitted beyond intended provider | Fully local |
| **Family Data Protection** | Children's names, ages, and locations exist only in local profile; never included verbatim in external API queries | Fully local |

### 10.2 Performance

| Metric | Target | Rationale |
|--------|--------|-----------|
| **Plan Generation Time** | < 3 minutes | User should not wait longer than making coffee |
| **Checkpoint Save** | < 100ms | Non-blocking state persistence |
| **Resume from Checkpoint** | < 5 seconds | Fast recovery on restart |
| **Memory Usage** | < 16GB RAM active | Allow headroom on 36GB M-series Mac |

### 10.3 Hardware Requirements

**Minimum (Development/Testing):**
- Apple M1 with 16GB unified memory
- OR Nvidia GPU with 8GB VRAM + 16GB system RAM
- 20GB free disk space

**Recommended (Production Use):**
- Apple M3 Max with 36GB+ unified memory
- OR Nvidia RTX 4090 with 24GB VRAM
- 50GB free disk space (for larger models)

### 10.3.1 Software Prerequisites

The following software must be present for Nexus to function. The launcher script (`start.command` / `start.sh`) handles all of these automatically — users who double-click the launcher never need to install anything manually.

| Prerequisite | Required Version | Auto-installed by Launcher | Detection Method |
|---|---|---|---|
| **Python** | 3.12+ | Yes (via `uv`) | `python3 --version` |
| **uv** | 0.11+ | Yes | `uv --version` |
| **Ollama** | latest | Yes (Homebrew on macOS, install script on Linux) | `ollama --version` |
| **Model** | `qwen3.5:9b` (6.6GB) | Yes (`ollama pull`) | `ollama list` |
| **Disk space** | 20GB free minimum | No (warning only) | `df` |
| **Port 7820** | Available | No (falls back to next available port) | Socket bind test |

> **Design note:** The launcher script is the recommended first-run path. Manual install via README remains supported for developers who prefer terminal workflows. Both paths converge at the same browser-based experience.

### 10.4 Reliability

| Requirement | Specification |
|-------------|---------------|
| **Graceful Degradation** | If an external API fails, continue with cached data annotated with staleness age. Agents governing hard constraints halt planning if they have no data (live or cached). Agents governing only soft constraints substitute a conservative default assumption and annotate the output. |
| **Idempotent Checkpoints** | Re-running from checkpoint produces identical results |
| **Error Recovery** | Agent failures don't crash the system; supervisor retries up to 2x before falling back to cached data or conservative default |
| **Audit Trail** | All decisions, data sources, and cache ages logged for debugging and user transparency |

### 10.5 Extensibility

| Requirement | Specification |
|-------------|---------------|
| **Plugin Architecture** | New agents can be added without modifying core graph |
| **Configurable Agents** | Agent behavior tunable via config files |
| **Swappable Models** | Different LLMs can be assigned to different agents |
| **API Adapters** | External data sources abstracted behind interfaces |

---

## 11. External Integrations & APIs

### 11.1 Required Data Sources (MVP)

| Data Category | Purpose | Privacy Consideration |
|---------------|---------|----------------------|
| **Weather Forecasts** | Validate safety — precipitation, AQI, lightning, temperature, daylight | Destination coordinates transmitted to provider |
| **Activity / Trail Database** | Discover activities and trails matching fitness and interest criteria | Search area revealed to provider |
| **Restaurant/Menu Data** | Verify dietary-compliant dining options exist near trail endpoint | Location-based search transmitted |
| **Routing/Drive Times** | Calculate routes and verify total driving time is within limits | Origin/destination pairs transmitted |
| **Cell Coverage** | Verify connectivity for family members who require it | Heuristic-based (distance from major roads/towns); no external API needed |

### 11.2 Integration Principles

| Principle | Specification |
|-----------|---------------|
| **Privacy-first provider selection** | Default to providers requiring no API key or minimal data exposure (e.g., government weather APIs); never transmit home address — use destination area or nearest town |
| **Configurable providers** | Each data category has a configurable provider, swappable without code changes. Defaults prioritize privacy; users can opt into higher-quality paid alternatives |
| **Aggressive caching** | All API responses are cached locally with appropriate time-to-live values to minimize external calls and enable offline re-planning |
| **Graceful failure** | If an API is unreachable: use cached data with age annotation for soft constraints; halt planning for hard constraints with no data |

> **Technical implementation:** Specific API providers, cache TTLs, Protocol-based abstractions, and provider implementations are specified in the [Technical Specification](nexus-tech-spec.md) §7 and §11.

---

## 12. Success Metrics

### 12.1 Product Metrics

| Metric | Definition | Target | Measurement |
|--------|------------|--------|-------------|
| **First-Pass Approval Rate** | % of plans approved without requiring user feedback | > 70% | `approved_first_try / total_plans` |
| **Hard Constraint Adherence** | % of hard constraints satisfied in every presented plan | 100% | Automated post-run validation |
| **Average Iterations** | Mean negotiation loops before consensus or best-compromise output | < 3 | `sum(iterations) / total_plans` |
| **Time to First Response** | Wall-clock time from request to first visible progress update in the browser | < 5 sec | Timestamp delta |
| **Time to Verified Plan** | Wall-clock time from request to fully verified plan ready for approval | < 3 min | Timestamp delta |
| **Post-Trip Feedback Rate** | % of approved plans where user completes a feedback entry | > 60% | Local usage log |
| **Post-Trip Success Rate** | % of completed trips rated as executed-as-planned (no hard failures encountered) | > 90% | Feedback responses |
| **Repeat Weekly Usage** | System used for actual planning in at least 3 of 4 consecutive weekends | ≥ 3/4 weeks | Local usage log |
| **Manual Edit Rate** | % of approved plans requiring user corrections after export | < 10% | User-reported |
| **Real-World Failure Rate** | % of approved plans with unexpected failures during execution (trail closed, restaurant wrong) | < 5% | User-reported post-trip |
| **User Trust Score** | Self-reported confidence in the plan at time of approval (1–5) | > 4.0 | Optional prompt after approval |

### 12.2 Technical Metrics

| Metric | Definition | Target | Measurement |
|--------|------------|--------|-------------|
| **Agent Success Rate** | % of agent invocations completing without error | > 99% | Error logs |
| **Checkpoint Reliability** | % of checkpoints successfully restored | 100% | Integration tests |
| **Memory Efficiency** | Peak RAM usage during planning | < 16GB | System monitoring |
| **API Call Efficiency** | External API calls per plan | < 20 | Call counting |

### 12.3 Showcase Goals

These metrics are tracked as a parallel objective alongside product metrics (see Section 2.1 dual-purpose declaration). They do not influence product prioritization.

| Metric | Target (6 months post-launch) | Measurement |
|--------|-------------------------------|-------------|
| **GitHub Stars** | 500+ | GitHub API |
| **Forks** | 50+ | GitHub API |
| **Community PRs** | 5+ meaningful contributions | GitHub |
| **LinkedIn Post Engagement** | 100+ reactions on launch post | LinkedIn analytics |
| **Blog/Article Mentions** | 3+ independent write-ups | Search alerts |
| **Derivative Projects** | 2+ "inspired by Nexus" builds | Community self-report |

---

## 13. Scope & Boundaries

### 13.1 In Scope (MVP)

- ✅ Weekend day-trip planning (single day)
- ✅ Multiple outdoor activity types: hiking/trail running, beach/waterfront, park/picnic/playground, biking, city exploring (walking tours, farmers markets, museums)
- ✅ Bay Area / Northern California geography
- ✅ Vegetarian dietary constraints
- ✅ Family of 4 (2 adults, 2 teens)
- ✅ Single-vehicle logistics
- ✅ English language only
- ✅ Local web UI (single browser tab at `localhost`)
- ✅ Markdown output for Obsidian sync

### 13.2 Out of Scope (MVP)

- ❌ Multi-day trips with lodging
- ❌ Niche/specialized activities (climbing, skiing, kayaking, horseback riding)
- ❌ International locations
- ❌ Complex dietary requirements (multiple allergies)
- ❌ Large groups (> 6 people)
- ❌ Real-time replanning during activity
- ❌ Mobile app (native)
- ❌ Cloud-hosted web UI
- ❌ Multi-language support

### 13.3 MVP Exit Criteria

The MVP is considered complete when all of the following are true:

| Criterion | Measurement |
|-----------|-------------|
| **End-to-end planning works** | `nexus` opens browser, user submits intent, receives a valid plan for at least 3 distinct activity/date combinations |
| **All hard constraints enforced** | Zero hard-constraint violations across 10 consecutive test runs |
| **Mid-planning input works** | User can add a constraint during planning and the system incorporates it without restarting |
| **Rejection loop works** | User can reject a plan with feedback and receive a revised plan that incorporates the feedback |
| **Setup flow works** | Browser-based setup creates a valid profile from scratch without requiring YAML editing |
| **Offline resilience** | System uses cached data and produces a plan when APIs are unreachable (with data-age annotations) |
| **Plan archive works** | Approved plans are saved as Markdown files to `~/.nexus/plans/` |
| **No internals exposed** | Output contains zero agent names, confidence scores, iteration counts, or architecture terms |

### 13.4 Assumptions

1. User has reliable home internet for initial API data fetching
2. User has hardware meeting minimum requirements
3. External APIs remain available and reasonably priced
4. User can provide accurate family member profiles upfront
5. User has a modern web browser (any browser that supports WebSocket/SSE)

### 13.5 Dependencies

| Dependency | Risk Level | Mitigation |
|------------|------------|------------|
| Ollama availability | Low | Well-established project; Docker fallback |
| LangGraph stability | Medium | Pin specific version; monitor releases |
| Weather API availability | Low | Multiple provider options |
| Trail data freshness | Medium | Community-sourced updates; manual override |

---

## 14. Open Questions

### 14.1 Resolved (kept for traceability)

| ID | Question | Resolution | Resolved In |
|----|----------|------------|-------------|
| Q1 | Sequential vs. parallel agent execution? | Parallel review phase, sequential drafting | Tech Spec §4.2 |
| Q2 | Partial API failure handling? | Use stale cache with age annotation for soft constraints; halt for hard constraints with no data | PRD §5.3, Tech Spec §7 |
| Q3 | Default model size for local inference? | qwen3.5:9b (context-efficient, fast) | Tech Spec §3.1 |
| Q4 | Orchestrator: LLM or deterministic? | Hybrid — LLM for intent parsing, rules for routing | Tech Spec §5.1 |
| Q5 | How to collect family profiles? | Browser-based guided setup (`/setup` page) primary; YAML as persistence format | PRD §9.3, UX Spec §4 |
| Q7 | Rejection feedback format? | Free text with suggested topics | PRD §6.4, UX Spec §7 |
| Q11 | UX for `NEEDS_INFO` state? | Use profile default with annotation; escalate only if missing data affects a hard constraint | PRD §6.3 |

### 14.2 Open

| ID | Question | Options | Notes |
|----|----------|---------|-------|
| Q6 | What notification mechanism for plan ready? | ~~Terminal output, System notification~~ | **Resolved:** Browser is the notification surface — plan renders inline with a visual transition. No system notification needed. |
| Q8 | What activity/trail database to use? | AllTrails export, Hiking Project API, Overpass/OSM, Custom scraped | Hiking Project API for trails (free, US-focused); Overpass/OSM for parks, beaches, bike routes, city POIs; evaluate API stability before committing |
| Q9 | How to get reliable menu data? | Yelp API, Google Places, Manual curation | Yelp API + manual override file is recommended; verify Yelp API terms |
| Q10 | Should historical plans be stored? | Yes (for learning), No (privacy), Optional | Recommend optional with explicit consent |

---

## 15. Glossary

| Term | Definition |
|------|------------|
| **Constraint Domain** | A category of requirements the system validates independently (weather, family, dining, logistics, safety) |
| **Hard Constraint** | A requirement that must be satisfied — the plan is discarded if breached |
| **Soft Constraint** | A best-effort requirement — noted in plan summary when unmet, but plan can proceed |
| **Consensus** | State where all constraint domains have approved the current proposal |
| **Human-in-the-Loop** | A deliberate pause in automated processing requiring human approval |
| **Iteration** | One complete cycle through the drafting → validation → revision loop |
| **Checkpoint** | A saved snapshot of planning state enabling pause/resume functionality |
| **Trade-off Disclosure** | The plain-English explanation of what was sacrificed and why in the final plan |

---

## Appendix A: Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-04-18 | Ved | Initial draft based on ideation session |
| 0.2.0 | 2026-04-18 | Ved | Incorporated ChatGPT product feedback: user-outcome-first executive summary; dual-purpose declaration; constraint hierarchy; two-speed UX model; trust-first output; best-compromise failure mode; narrowed MVP; fixed NEEDS_INFO routing; clarified privacy claim; product behavior metrics |
| 0.3.0 | 2026-04-18 | Ved | Incorporated Gemini product feedback: showcase boundary (code quality, not UX exposure); negotiation log moved to `--debug` only; primary output changed from Markdown to local HTML opened in browser; `[UNVERIFIED]` draft replaced with live status messages in terminal; user-facing copy purged of agent names, confidence %, iteration counts; no-perfect-plan output changed from 3-option menu to single confident recommendation; rejection flow designed to be effortless |
| 0.4.0 | 2026-04-18 | Ved | Incorporated Perplexity product feedback: §6.1 architecture risk note mapping 7 agents to 4 product-facing responsibilities; `nexus feedback` post-trip command added as P0 (F17); §8.2 post-MVP gate requiring 4 proven weekends before new features are scoped; "why this and not that" optional disclosure added to approved plan output artifact; "Time to Quick Draft" renamed "Time to First Response" (terminal status line, not draft plan); "Post-Trip Feedback Rate" and "Post-Trip Success Rate" added as first-class product metrics |
| 0.5.0 | 2026-04-18 | Ved | Separation of concerns cleanup: removed ~500 lines of technical implementation details (agent specs, Pydantic schemas, state reducers, execution loop diagrams) — migrated to Tech Spec; removed ~130 lines of UX implementation details (HTML mockups, terminal output examples, visual design) — migrated to UX Spec; §6 rewritten as product-level "System Behavior" (constraint domains, execution flow, consensus rules); §7 simplified to "Data the System Manages"; §9 rewritten as product-level UX requirements; §11 simplified to integration principles; added §5.3 constraint conflict resolution priority; added §13.3 MVP exit criteria; added §6.4 human rejection loop limits; resolved open questions Q1–Q5, Q7, Q11; updated glossary to use product terminology; updated companion doc links |
| 0.6.0 | 2026-04-18 | Ved | Interaction model pivot: CLI-first replaced with local web UI (single browser tab at `localhost`). Rationale: eliminates split-surface interaction (terminal → browser → terminal), enables mid-planning constraint injection, makes approve/reject native, and allows family members to view plans without terminal skills. §5.1 updated with collaborative planning innovation; §9 rewritten for browser-first experience; §8.1 F11 changed from HTML file to web UI; F21 Mobile Companion removed (localhost already accessible on phone); §13 scope updated; §13.3 MVP exit criteria updated to include mid-planning input; Q6 resolved (browser is the notification surface) |
| 0.7.0 | 2026-04-18 | Ved | Activity-flexible MVP: replaced hiking-only scope with support for 5 outdoor activity types (hiking/trail running, beach/waterfront, park/picnic/playground, biking, city exploring). Users select preferred activities during setup. §3.1 persona broadened; §3.2 added beach and city scenarios; §4.3 workflow generalized; §7 family profiles use `comfort_distance` instead of `hiking_distance`; §9.5 plan content generalized from trail-specific to activity-generic; §13 scope rewritten; Q8 updated for multi-activity data sources |

---

## Appendix B: Related Documents

| Document | Status | Purpose |
|----------|--------|---------|
| [Technical Specification](nexus-tech-spec.md) | v1.3.0-draft | Implementation details, APIs, data models, architecture decisions |
| [UX Specification](nexus-ux-spec.md) | v1.3.0-draft | Interface designs, user flows, visual design |
| Implementation Plan | Not Started | Phased development roadmap |

---

*End of Document*
