"""
User-facing progress messages for each graph node.

Maps internal node names to copy that follows UX §5.5 — no agent names,
no architecture terms, no percentages.

Iteration-aware messages for re-plan loops are defined as lambda
so they can incorporate the iteration count at call time.
"""

from __future__ import annotations

# Static (single-pass) node messages
NODE_MESSAGES: dict[str, str] = {
    "parse_intent": "Understanding your request...",
    "draft_proposal": "Finding the right activity...",
    "review_meteorology": "Checking the weather...",
    "review_family": "Making sure everyone's covered...",
    "review_nutrition": "Finding a good place to eat...",
    "review_logistics": "Mapping the route...",
    "check_consensus": "Reviewing everything...",
    "review_safety": "Final safety check...",
    "synthesize_plan": "Pulling your plan together...",
    "save_plan": "Saving your plan...",
}

# Iteration-aware messages (replanning loop): format with iteration number
ITERATION_NODE_MESSAGES: dict[str, str] = {
    "draft_proposal": "That didn't quite work — finding another option...",
    "review_meteorology": "Re-checking the weather for this option...",
    "review_family": "Making sure this one works for everyone...",
    "review_nutrition": "Looking for a better restaurant option...",
    "review_logistics": "Recalculating the route...",
    "check_consensus": "Re-evaluating...",
}

# Detailed context shown to the user while each step is active.
# Keep these entirely free of internal node/agent names.
NODE_CONTEXT: dict[str, str] = {
    "parse_intent": (
        "Reading your request and identifying key requirements — activity type, "
        "fitness level, dietary needs, and who's joining."
    ),
    "draft_proposal": (
        "Searching OpenStreetMap for trails, parks, and outdoor spots that match "
        "what you asked for."
    ),
    "review_meteorology": (
        "Fetching live weather, air quality, and daylight hours for your target "
        "date from Open-Meteo."
    ),
    "review_family": (
        "Verifying the activity suits everyone in your group and that there's "
        "cell coverage on-site."
    ),
    "review_nutrition": (
        "Looking for nearby restaurants and food options that meet your dietary "
        "restrictions."
    ),
    "review_logistics": (
        "Calculating driving time and turn-by-turn route from your home using "
        "live routing data."
    ),
    "check_consensus": (
        "All checks are being weighed — if anything's off, Nexus will try a "
        "different option automatically."
    ),
    "review_safety": (
        "Final pass — confirming weather, route, and medical access are all "
        "within safe limits."
    ),
    "synthesize_plan": (
        "Writing your personalised plan narrative. Almost there!"
    ),
    "save_plan": (
        "Saving the finished plan to disk."
    ),
}


# ── Agent trace metadata ────────────────────────────────────────────────────
# Exposed to the planning UI so users can learn the multi-agent architecture.
# Each entry describes one LangGraph node: its class name, LangGraph role,
# which tools/APIs it calls, and whether it makes LLM calls.

AGENT_TRACE: dict[str, dict] = {
    "parse_intent": {
        "class": "IntentParser",
        "role": "Entry node — parses natural-language intent into structured state",
        "llm": True,
        "tools": [],
        "langgraph": "Linear node (START → parse_intent → draft_proposal)",
        "description": (
            "Uses the LLM to extract activity type, group size, dietary needs, "
            "fitness level, and date from free-text input. Writes to "
            "WeekendPlanState so all downstream agents share a single structured "
            "source of truth."
        ),
    },
    "draft_proposal": {
        "class": "ObjectiveAgent",
        "role": "Fan-out source — proposes an activity then spawns parallel reviewers",
        "llm": True,
        "tools": ["Overpass API (OpenStreetMap)"],
        "langgraph": "Conditional fan-out → [review_meteorology, review_family, review_nutrition, review_logistics]",
        "description": (
            "Queries OpenStreetMap via Overpass API for candidate trails and "
            "outdoor spots. Chooses one proposal and writes it to state. "
            "LangGraph then fans out to four reviewer agents in parallel."
        ),
    },
    "review_meteorology": {
        "class": "MeteorologyAgent",
        "role": "Parallel reviewer — weather & air quality",
        "llm": True,
        "tools": ["Open-Meteo API"],
        "langgraph": "Parallel branch → check_consensus",
        "description": (
            "Fetches hourly forecast, AQI, and daylight hours from Open-Meteo. "
            "Returns an AgentVerdict: PASS, NEEDS_INFO, or REJECT. Rejection "
            "triggers a re-plan loop in check_consensus."
        ),
    },
    "review_family": {
        "class": "FamilyCoordinatorAgent",
        "role": "Parallel reviewer — group suitability & cell coverage",
        "llm": True,
        "tools": ["Overpass API (cell tower lookup)"],
        "langgraph": "Parallel branch → check_consensus",
        "description": (
            "Checks that the proposed activity suits every family member's age "
            "and interests. Also queries OpenStreetMap for cell tower density "
            "to flag areas without coverage."
        ),
    },
    "review_nutrition": {
        "class": "NutritionalAgent",
        "role": "Parallel reviewer — meal planning near the activity",
        "llm": True,
        "tools": ["Google Places API", "Overpass API"],
        "langgraph": "Parallel branch → check_consensus",
        "description": (
            "Searches for restaurants within the driving radius that match "
            "dietary restrictions. Falls back to Overpass if Google Places "
            "is unavailable. Writes a MealPlan to state."
        ),
    },
    "review_logistics": {
        "class": "LogisticsAgent",
        "role": "Parallel reviewer — routing & drive-time",
        "llm": False,
        "tools": ["OSRM routing API"],
        "langgraph": "Parallel branch → check_consensus",
        "description": (
            "Calculates driving time and turn-by-turn route from home to the "
            "activity using OSRM (open-source routing). No LLM call — pure "
            "deterministic tool use."
        ),
    },
    "check_consensus": {
        "class": "OrchestratorAgent",
        "role": "Convergence node — aggregates verdicts and routes the graph",
        "llm": True,
        "tools": [],
        "langgraph": "Conditional edges → [draft_proposal (re-plan), review_safety, END]",
        "description": (
            "Collects all four reviewer verdicts and asks the LLM to decide: "
            "proceed to safety review, loop back to draft_proposal with a "
            "new constraint, or give up. This is the main control-flow brain "
            "of the LangGraph pipeline."
        ),
    },
    "review_safety": {
        "class": "SafetyAgent",
        "role": "Gate node — blocks unsafe plans before synthesis",
        "llm": True,
        "tools": [],
        "langgraph": "Conditional edges → [synthesize_plan (safe), END (unsafe)]",
        "description": (
            "Final guard before the plan is written. Checks that weather, "
            "driving time, and emergency access all meet safe thresholds. "
            "Unsafe plans are dropped rather than shown to the user."
        ),
    },
    "synthesize_plan": {
        "class": "PlanSynthesizer",
        "role": "Output node — writes the human-readable plan narrative",
        "llm": True,
        "tools": [],
        "langgraph": "Linear node → save_plan (with interrupt_after for human-in-loop review)",
        "description": (
            "Takes all state accumulated by reviewers and calls the LLM to "
            "produce a structured JSON narrative. The graph is compiled with "
            "interrupt_after=[\"synthesize_plan\"], so LangGraph pauses here "
            "and allows human-in-the-loop approval before saving."
        ),
    },
    "save_plan": {
        "class": "SavePlanAgent",
        "role": "Sink node — persists the approved plan",
        "llm": False,
        "tools": ["SQLite (AsyncSqliteSaver checkpoint)", "Disk (HTML file)"],
        "langgraph": "Linear node → END",
        "description": (
            "Renders the plan to HTML via Jinja2 and writes it to disk. "
            "Also records stats (plan count, approval rate) to stats.db. "
            "No LLM call — pure I/O."
        ),
    },
}

# Ordered list of nodes as they appear in the graph (for display)
AGENT_ORDER: list[str] = [
    "parse_intent",
    "draft_proposal",
    "review_meteorology",
    "review_family",
    "review_nutrition",
    "review_logistics",
    "check_consensus",
    "review_safety",
    "synthesize_plan",
    "save_plan",
]


def message_for(node_name: str, iteration: int = 1) -> str:
    """Return the user-facing progress message for a node at the given iteration."""
    if iteration > 1 and node_name in ITERATION_NODE_MESSAGES:
        return ITERATION_NODE_MESSAGES[node_name]
    return NODE_MESSAGES.get(node_name, f"Working...")


def context_for(node_name: str) -> str:
    """Return the detailed context description shown while a node is active."""
    return NODE_CONTEXT.get(node_name, "")

