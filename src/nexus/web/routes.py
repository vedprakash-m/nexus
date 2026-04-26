"""
All FastAPI routes — pages, API endpoints, WebSocket.

Concurrency policy (Tech §9.8):
- One active planning run per request_id via asyncio.Lock
- Locks are in-memory (lost on restart — benign for local tool)
# NOTE: locks are not persisted across server restarts

HITL resume (Tech §8.3):
- approve_plan(): resume via ainvoke(None)
- reject_plan(): aupdate_state() then ainvoke(None)
- constraint injection: aupdate_state() to pending_constraints
"""

from __future__ import annotations

import asyncio
import inspect as _inspect
import json
import logging
from contextlib import asynccontextmanager as _acm
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from nexus.config import NexusConfig
from nexus.web.schemas import (
    ApiKeyRequest,
    ApiKeyStatus,
    ApproveResponse,
    ConstraintRequest,
    FeedbackRequest,
    PlanRequest,
    PlanResponse,
    PreflightStatus,
    RejectRequest,
    SetupRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint helper — ISSUE-04
# ─────────────────────────────────────────────────────────────────────────────

# All custom types that the msgpack deserializer is allowed to restore.
# Keeping this list complete prevents LangGraph 'unregistered type' warnings.
_ALLOWED_MSGPACK_MODULES = [
    ("nexus.state.schemas", "UserProfile"),
    ("nexus.state.schemas", "FamilyProfile"),
    ("nexus.state.schemas", "PlanRequirements"),
    ("nexus.state.schemas", "ActivityProposal"),
    ("nexus.state.schemas", "FamilyActivity"),
    ("nexus.state.schemas", "RestaurantRecommendation"),
    ("nexus.state.schemas", "AgentVerdict"),
    ("nexus.tools.models", "WeatherForecast"),
    ("nexus.tools.models", "RouteResult"),
]


@_acm
async def _open_checkpointer(db_path: Path):
    """Shared async context manager for AsyncSqliteSaver — applies the msgpack allowlist.

    All five call sites in routes.py route through this helper so the allowlist
    and path resolution are consistent (ISSUE-04).
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    # Runtime version guard — allowed_msgpack_modules added post-3.0.0
    _sig = _inspect.signature(AsyncSqliteSaver.from_conn_string)
    if "allowed_msgpack_modules" in _sig.parameters:
        async with AsyncSqliteSaver.from_conn_string(
            str(db_path),
            allowed_msgpack_modules=_ALLOWED_MSGPACK_MODULES,
        ) as cp:
            yield cp
    else:
        import warnings

        warnings.warn(
            "AsyncSqliteSaver.from_conn_string does not accept allowed_msgpack_modules "
            "— msgpack warnings may appear. Upgrade langgraph-checkpoint-sqlite>=3.0.0.",
            stacklevel=2,
        )
        async with AsyncSqliteSaver.from_conn_string(str(db_path)) as cp:
            yield cp


# In-memory concurrency control (not persisted across restarts)
# NOTE: locks and tasks are not persisted across server restarts
_active_locks: dict[str, asyncio.Lock] = {}
_active_tasks: dict[str, asyncio.Task] = {}  # for stop_planning cancellation (task 6.12)
_plan_contexts: dict[str, dict] = {}  # lightweight context for planning page display
_plan_context_timestamps: dict[str, float] = {}  # ISSUE-08: TTL eviction support


def _get_config(request: Request) -> NexusConfig:
    return request.app.state.config


def _home_area_label(config: NexusConfig) -> str | None:
    """ISSUE-12: Human-readable location label for the planning page.

    Priority: home_address first char → lat/lon string → None (hide the field).
    The default SF placeholder coordinates (37.7749, -122.4194) are suppressed
    so a fresh profile without real coordinates shows nothing rather than
    'San Francisco'.
    """
    if config.user.home_address:
        return config.user.home_address.split(",")[0].strip()
    lat, lon = config.user.home_coordinates
    _SF_DEFAULT = (37.7749, -122.4194)
    if (lat, lon) != _SF_DEFAULT:
        return f"{lat:.2f}°N, {abs(lon):.2f}°{'W' if lon < 0 else 'E'}"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Page routes
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    config = _get_config(request)
    profile_path = config.paths.base_dir / "profile.yaml"
    if not profile_path.exists():
        return RedirectResponse("/setup")
    from nexus.stats import get_monthly_stats, get_recent_plans, get_summary

    stats_db = config.paths.base_dir / "stats.db"
    stats = get_summary(stats_db)
    monthly_stats = get_monthly_stats(stats_db)
    recent_plans = get_recent_plans(stats_db)
    return _html_page(
        request,
        "index.html",
        context={
            "stats": stats,
            "monthly_stats": monthly_stats,
            "recent_plans": recent_plans,
            "config": config,
        },
    )


@router.get("/preflight", response_class=HTMLResponse)
async def preflight_page(request: Request) -> HTMLResponse:
    config = _get_config(request)
    status = await preflight_check(request)
    return _html_page(
        request,
        "preflight.html",
        context={
            "status": status,
            "model_name": config.models.local_model,
        },
    )


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request) -> HTMLResponse:
    config = _get_config(request)
    profile_path = config.paths.base_dir / "profile.yaml"
    profile_exists = profile_path.exists()
    places_key = config.tools.api_keys.get("GOOGLE_PLACES_API_KEY", "")

    # Load actual profile so the form pre-fills for editing
    profile = None
    if profile_exists:
        try:
            profile = NexusConfig.load(profile_path)
        except Exception as _exc:
            logger.warning("Could not load profile for setup page: %s", _exc)

    return _html_page(
        request,
        "setup.html",
        context={
            "profile_exists": profile_exists,
            "profile": profile,
            "places_configured": bool(places_key),
            "places_key_prefix": places_key[:4] if places_key else None,
        },
    )


@router.get("/plan", response_class=HTMLResponse)
async def plan_page(request: Request) -> HTMLResponse:
    port = request.url.port or 7820
    from nexus.web.messages import AGENT_ORDER, AGENT_TRACE

    return _html_page(
        request,
        "planning.html",
        context={
            "port": port,
            "agent_trace": AGENT_TRACE,
            "agent_order": AGENT_ORDER,
        },
    )


@router.get("/plans", response_class=HTMLResponse)
async def plans_list_page(request: Request) -> HTMLResponse:
    config = _get_config(request)
    from nexus.stats import get_recent_plans as _get_recent

    stats_db = config.paths.base_dir / "stats.db"
    plans = _get_recent(stats_db, limit=50)
    return _html_page(request, "history.html", context={"plans": plans})


@router.get("/plans/{request_id}", response_class=HTMLResponse)
async def plan_detail_page(request: Request, request_id: str) -> HTMLResponse:
    """
    Serve the completed plan page for a given request_id.

    Loads `output_html` from the LangGraph SQLite checkpoint (written by
    plan_synthesizer after GAP-1 fix).  Falls back to an empty plan card
    if the checkpoint is missing or the run is still in progress.
    """
    config = _get_config(request)
    checkpoint_path = config.paths.checkpoints_dir / "nexus.db"

    if checkpoint_path.exists():
        try:
            from nexus.graph.planner import build_planning_graph

            async with _open_checkpointer(checkpoint_path) as checkpointer:
                graph = build_planning_graph(checkpointer=checkpointer)
                thread_config = {"configurable": {"thread_id": request_id}}
                snapshot = await graph.aget_state(thread_config)
                output_html: str | None = (snapshot.values or {}).get("output_html")

            if output_html:
                return HTMLResponse(content=output_html)
        except Exception as exc:
            logger.warning("Could not load checkpoint for plan %s: %s", request_id, exc)

    # Fallback: plan still running or checkpoint not found
    return _html_page(
        request,
        "plan.html",
        context={"request_id": request_id, "plan": None, "confidence_labels": []},
    )


# ─────────────────────────────────────────────────────────────────────────────
# API routes
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/api/plans", response_model=PlanResponse)
async def start_planning(request: Request, body: PlanRequest) -> PlanResponse:
    """Start a new planning run. Returns request_id for WebSocket subscription."""
    config = _get_config(request)
    from nexus.graph.runner import run_planning

    # Build target_date
    target_date: date | None = None
    if body.target_date:
        try:
            target_date = date.fromisoformat(body.target_date)
        except ValueError:
            raise HTTPException(
                status_code=422, detail="Invalid target_date format — expected YYYY-MM-DD"
            )

    # Launch planning in background (WebSocket streams progress)
    request_id = _new_request_id()
    lock = asyncio.Lock()
    _active_locks[request_id] = lock

    # Store lightweight context for the planning page to display as inputs
    import time as _time

    _now_ts = _time.monotonic()
    # ISSUE-08: Evict stale contexts older than 2 hours before inserting
    _stale = [k for k, t in _plan_context_timestamps.items() if _now_ts - t > 7200]
    for _sk in _stale:
        _plan_contexts.pop(_sk, None)
        _plan_context_timestamps.pop(_sk, None)

    _plan_contexts[request_id] = {
        "intent": body.intent.strip(),
        "target_date": target_date.strftime("%A, %B %-d, %Y") if target_date else "This weekend",
        "name": config.user.name,
        "fitness_level": config.user.fitness_level.capitalize(),
        "dietary_restrictions": config.user.dietary_restrictions or [],
        "max_driving_minutes": config.user.max_driving_minutes,
        "home_area": _home_area_label(config),  # ISSUE-12
        "family_members": [{"name": m.name, "age": m.age} for m in config.family.members],
        "preferred_activities": config.user.preferred_activities or [],
    }
    _plan_context_timestamps[request_id] = _time.monotonic()

    # Record plan start for stats tracking (UX §9.4, task 6.17)
    from nexus.stats import record_plan_started

    stats_db = config.paths.base_dir / "stats.db"
    activity_type = body.intent.strip()[:80] if body.intent else None
    record_plan_started(stats_db, request_id, activity_type)

    async def _run() -> None:
        from nexus.web.progress import get_or_create as _prog_get

        async with lock:
            try:
                _progress = _prog_get(request_id)
                await run_planning(
                    body.intent,
                    config,
                    progress=_progress,
                    request_id=request_id,
                    target_date=target_date,
                )
            except asyncio.CancelledError:
                # stop_planning message received — emit cancellation event (task 6.12)
                logger.info("Planning run cancelled by user for %s", request_id)
                try:
                    await _prog_get(request_id).on_planning_error(
                        "cancelled", "Planning stopped by user"
                    )
                except Exception:
                    pass
            except Exception as exc:
                logger.error("Planning run failed for %s: %s", request_id, exc)
                try:
                    await _prog_get(request_id).on_planning_error("internal_error", str(exc))
                except Exception:
                    pass
            finally:
                _active_locks.pop(request_id, None)
                _active_tasks.pop(request_id, None)
                # ISSUE-08: Remove context entry once planning run lifecycle ends
                _plan_contexts.pop(request_id, None)
                _plan_context_timestamps.pop(request_id, None)
                # ISSUE-08: Remove context entry once planning run lifecycle ends
                _plan_contexts.pop(request_id, None)
                _plan_context_timestamps.pop(request_id, None)

    task = asyncio.create_task(_run())
    _active_tasks[request_id] = task
    return PlanResponse(request_id=request_id)


@router.get("/api/plans/{request_id}/context")
async def get_plan_context(request_id: str) -> JSONResponse:
    """Return the lightweight planning inputs context for display on the planning page."""
    ctx = _plan_contexts.get(request_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="Context not found")
    return JSONResponse(content=ctx)


@router.post("/api/plans/{request_id}/approve", response_model=ApproveResponse)
async def approve_plan(request: Request, request_id: str) -> ApproveResponse:
    """Resume graph after HITL interrupt — saves plan to disk."""
    config = _get_config(request)
    checkpoint_path = config.paths.checkpoints_dir / "nexus.db"

    if request_id in _active_locks and _active_locks[request_id].locked():
        raise HTTPException(status_code=409, detail="Planning run is still in progress")

    import nexus.runtime as runtime
    from nexus.graph.planner import build_planning_graph
    from nexus.llm.router import ModelRouter
    from nexus.tools.registry import build_registry

    async with _open_checkpointer(checkpoint_path) as checkpointer:
        graph = build_planning_graph(
            checkpointer=checkpointer,
            model_router=runtime.model_router or ModelRouter(config),
            tool_registry=runtime.tool_registry or build_registry(config),
            nexus_config=config,
        )
        thread_config = {"configurable": {"thread_id": request_id}}

        # Determine approval pass number + verify plan is ready for approval.
        # Using checkpoint state instead of in-memory lock (which is removed
        # as soon as run_planning() returns, before approve is called).
        rejection_count = 0
        pre_state = None
        try:
            pre_state = await graph.aget_state(thread_config)
            if pre_state and pre_state.values:
                rejection_count = pre_state.values.get("human_rejection_count", 0)
                if not pre_state.values.get("output_html"):
                    raise HTTPException(
                        status_code=409,
                        detail="Plan is not ready for approval yet — still in progress",
                    )
        except HTTPException:
            raise
        except Exception:
            pass

        await graph.ainvoke(None, config=thread_config)

    # Record approval in stats (UX §9.4, task 6.17)
    from nexus.stats import record_plan_approved

    stats_db = config.paths.base_dir / "stats.db"
    record_plan_approved(stats_db, request_id, pass_number=rejection_count + 1)

    return ApproveResponse(request_id=request_id, status="approved")


@router.post("/api/plans/{request_id}/reject")
async def reject_plan(request: Request, request_id: str, body: RejectRequest) -> dict:
    """Inject human feedback and resume planning from draft_proposal.

    Enforces PRD §6.4 rejection limits:
      • Same feedback submitted twice in a row → offer_anyway hint (client may present
        the existing plan as-is).
      • 5 total rejections for one request_id → suggest_manual hint (stop re-planning).
    """
    config = _get_config(request)
    checkpoint_path = config.paths.checkpoints_dir / "nexus.db"

    # ── 1. Read current checkpoint state ────────────────────────────────────
    current_count: int = 0
    last_feedback: str = ""
    async with _open_checkpointer(checkpoint_path) as _ckpt:
        from nexus.graph.planner import build_planning_graph as _bpg

        _g = _bpg(checkpointer=_ckpt)
        _snap = await _g.aget_state({"configurable": {"thread_id": request_id}})
        if _snap and _snap.values:
            current_count = _snap.values.get("human_rejection_count", 0)
            last_feedback = _snap.values.get("human_feedback", "") or ""

    new_count = current_count + 1

    # ── 2. Hard limit: 5 total rejections → suggest manual planning ─────────
    if current_count >= 4:
        logger.info("Rejection limit reached for %s (%d rejections)", request_id, new_count)
        return {
            "request_id": request_id,
            "status": "limit_reached",
            "suggest_manual": True,
            "message": (
                "We've tried 5 times and can't find a plan that works. "
                "Consider planning this trip manually."
            ),
        }

    # ── 3. Repeated feedback: offer to accept existing plan ─────────────────
    is_repeated = (
        not body.force  # force=True bypasses repeat detection (REPLAN ANYWAY)
        and current_count >= 1
        and bool(last_feedback)
        and last_feedback.strip().lower() == body.reason.strip().lower()
    )

    # ── 4. Update state + resume in background (fresh connection) ───────────
    async def _resume() -> None:
        from nexus.web.progress import get_or_create as _prog_get

        lock = _active_locks.setdefault(request_id, asyncio.Lock())
        async with lock:
            # Reset progress so the browser sees fresh events (not stale plan_ready)
            _progress = _prog_get(request_id)
            _progress._completed = []
            _progress._iteration = 1

            import nexus.runtime as _runtime

            async with _open_checkpointer(checkpoint_path) as _ckpt2:
                from nexus.graph.planner import build_planning_graph as _bpg2
                from nexus.llm.router import ModelRouter as _MR
                from nexus.tools.registry import build_registry as _br
                from nexus.state.schemas import AgentVerdict as _AV

                g2 = _bpg2(
                    checkpointer=_ckpt2,
                    model_router=_runtime.model_router or _MR(config),
                    tool_registry=_runtime.tool_registry or _br(config),
                    nexus_config=config,
                )
                thread_cfg = {"configurable": {"thread_id": request_id}}
                # Reset verdicts with neutral placeholders so merge_verdicts
                # (which is an upsert-by-agent-name reducer) actually clears them.
                # Passing an empty list is a no-op in the reducer.
                cleared_verdicts = [
                    _AV(
                        agent_name=name,
                        verdict="NEEDS_INFO",
                        is_hard_constraint=False,
                        confidence=0.0,
                    )
                    for name in [
                        "meteorology",
                        "family_coordinator",
                        "nutritional",
                        "logistics",
                        "safety",
                    ]
                ]
                await g2.aupdate_state(
                    thread_cfg,
                    {
                        "human_feedback": body.reason,
                        "iteration_count": 0,
                        "current_verdicts": cleared_verdicts,
                        "human_rejection_count": new_count,
                    },
                    as_node="draft_proposal",
                )

                # Stream events to broadcast progress to the planning page WebSocket
                _RESUME_NODES = frozenset(
                    [
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
                )

                async def _stream_resume() -> None:
                    async for _evt in g2.astream_events(None, config=thread_cfg, version="v2"):
                        _etype = _evt.get("event", "")
                        _nname = _evt.get("name", "")
                        if _nname not in _RESUME_NODES:
                            continue
                        if _etype == "on_chain_start":
                            await _progress.on_node_start(_nname)
                        elif _etype == "on_chain_end":
                            await _progress.on_node_complete(_nname)

                try:
                    await asyncio.wait_for(_stream_resume(), timeout=90.0)
                except asyncio.TimeoutError:
                    await _progress.on_planning_error(
                        "timeout", "Re-planning timed out after 90 seconds"
                    )
                    return
                except Exception as _exc:
                    logger.error("Replan stream error for %s: %s", request_id, _exc)
                    await _progress.on_planning_error("internal_error", str(_exc))
                    return

                # Emit plan_ready with the new output_html
                try:
                    _snap = await g2.aget_state(thread_cfg)
                    _out_html = (_snap.values or {}).get("output_html")
                    if _out_html:
                        await _progress.on_plan_ready(_out_html)
                    else:
                        await _progress.on_planning_error(
                            "no_output", "Re-planning completed but produced no output"
                        )
                except Exception as _snap_exc:
                    logger.warning(
                        "Could not emit plan_ready after replan for %s: %s", request_id, _snap_exc
                    )

    # Only start replanning immediately when feedback is NOT a repeat.
    # For repeated feedback, offer_anyway=True lets the user choose explicitly.
    if not is_repeated:
        asyncio.create_task(_resume())

    # Record rejection in stats (UX §9.4, task 6.17)
    from nexus.stats import record_plan_rejected

    stats_db = config.paths.base_dir / "stats.db"
    record_plan_rejected(stats_db, request_id)

    response: dict = {
        "request_id": request_id,
        "status": "rejected",
        "message": "Re-planning started",
    }
    if is_repeated:
        response["status"] = "offer_anyway"
        response["message"] = "Same feedback detected — replan manually if you wish."
        response["offer_anyway"] = True
        response["hint"] = (
            "You've given the same feedback before — would you like to proceed with the existing plan instead?"
        )
    return response


@router.post("/api/plans/{request_id}/constraint")
async def add_constraint(request: Request, request_id: str, body: ConstraintRequest) -> dict:
    """Inject a mid-flight constraint — appended to pending_constraints queue."""
    config = _get_config(request)
    checkpoint_path = config.paths.checkpoints_dir / "nexus.db"

    async with _open_checkpointer(checkpoint_path) as checkpointer:
        from nexus.graph.planner import build_planning_graph

        graph = build_planning_graph(checkpointer=checkpointer)
        thread_config = {"configurable": {"thread_id": request_id}}
        # Get current pending_constraints and append new one
        current_state = await graph.aget_state(thread_config)
        if current_state.values:
            existing = list(current_state.values.get("pending_constraints", []))
            existing.append(body.constraint)
            await graph.aupdate_state(
                thread_config,
                {"pending_constraints": existing},
            )

    return {"request_id": request_id, "constraint_added": body.constraint}


@router.post("/api/plans/{request_id}/feedback")
async def submit_feedback(request: Request, request_id: str, body: FeedbackRequest) -> dict:
    """Store human feedback for the plan."""
    config = _get_config(request)
    checkpoint_path = config.paths.checkpoints_dir / "nexus.db"

    async with __import__(
        "langgraph.checkpoint.sqlite.aio", fromlist=["AsyncSqliteSaver"]
    ).AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        from nexus.graph.planner import build_planning_graph

        graph = build_planning_graph(checkpointer=checkpointer)
        thread_config = {"configurable": {"thread_id": request_id}}
        await graph.aupdate_state(thread_config, {"human_feedback": body.feedback})

    # Append feedback to the existing plan Markdown file (UX §9.5 / task 7.14).
    # The plan file lives at plans_dir/{date}-{slug}.md.  We recover the
    # activity_name and target_date from the checkpoint state.
    config2 = _get_config(request)
    try:
        from nexus.output.filenames import plan_filename

        checkpoint_path2 = config2.paths.checkpoints_dir / "nexus.db"
        plan_proposal = None
        plan_date = None
        if checkpoint_path2.exists():
            async with _open_checkpointer(checkpoint_path2) as _ckpt:
                from nexus.graph.planner import build_planning_graph as _bpg

                _g = _bpg(checkpointer=_ckpt)
                _snap = await _g.aget_state({"configurable": {"thread_id": request_id}})
                if _snap and _snap.values:
                    plan_proposal = _snap.values.get("primary_activity")
                    plan_date = _snap.values.get("target_date")

        if plan_proposal is not None and plan_date is not None:
            filename = plan_filename(plan_proposal.activity_name, plan_date)
            plan_path = config2.paths.plans_dir / filename
            if plan_path.exists():
                from datetime import datetime as _dt, timezone as _tz

                feedback_block = (
                    "\n\n## Post-Trip Feedback\n\n"
                    f"_Recorded: {_dt.now(tz=_tz.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
                    f"{body.feedback}\n"
                )
                with plan_path.open("a", encoding="utf-8") as _f:
                    _f.write(feedback_block)
                logger.info("Feedback appended to %s", plan_path)
            else:
                logger.warning("Plan file not found for feedback: %s", plan_path)
        else:
            logger.warning(
                "Could not resolve plan file for request %s — feedback not appended", request_id
            )
    except Exception as _fb_exc:
        logger.warning("Feedback append failed for %s: %s", request_id, _fb_exc)

    # Track feedback completion rate (UX §15.1)
    from nexus.stats import record_feedback_given

    stats_db = config.paths.base_dir / "stats.db"
    record_feedback_given(stats_db, request_id)

    return {"request_id": request_id, "status": "feedback_saved"}


@router.post("/api/plans/{request_id}/trust-score")
async def submit_trust_score(request: Request, request_id: str, body: dict) -> dict:
    """
    Record user trust score (1–5) for an approved plan — PRD §12.1.

    Body: {"score": int}  where score is 1–5.
    Writes to stats.db and appends to the plan Markdown file's YAML frontmatter.
    """
    score = body.get("score")
    if not isinstance(score, int) or not (1 <= score <= 5):
        raise HTTPException(status_code=422, detail="score must be an integer 1–5")

    config = _get_config(request)
    from nexus.stats import record_trust_score

    stats_db = config.paths.base_dir / "stats.db"
    try:
        record_trust_score(stats_db, request_id, score)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"request_id": request_id, "trust_score": score, "status": "recorded"}


@router.post("/api/setup")
async def setup_profile(request: Request, body: SetupRequest) -> dict:
    """Save profile.yaml via ruamel.yaml (preserves comments on round-trip)."""
    config = _get_config(request)

    # Geocode home address → lat/lon.
    # Uses Google Geocoding API when GOOGLE_PLACES_API_KEY is configured,
    # otherwise falls back to Nominatim (free OSM, no key required).
    import httpx as _httpx

    home_lat: float | None = None
    home_lon: float | None = None
    _google_key = config.tools.api_keys.get("GOOGLE_PLACES_API_KEY", "")

    async def _geocode_google(address: str, key: str) -> tuple[float, float] | None:
        async with _httpx.AsyncClient(timeout=8.0) as _client:
            _resp = await _client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": key},
            )
            _resp.raise_for_status()
            _data = _resp.json()
            if _data.get("status") == "OK" and _data.get("results"):
                _loc = _data["results"][0]["geometry"]["location"]
                return float(_loc["lat"]), float(_loc["lng"])
        return None

    async def _geocode_nominatim(address: str) -> tuple[float, float] | None:
        async with _httpx.AsyncClient(timeout=8.0) as _client:
            _resp = await _client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "limit": "1"},
                headers={"User-Agent": "Nexus/1.0 (local-first weekend planner)"},
            )
            _resp.raise_for_status()
            _results = _resp.json()
            if _results:
                return float(_results[0]["lat"]), float(_results[0]["lon"])
        return None

    try:
        coords: tuple[float, float] | None = None
        if _google_key:
            coords = await _geocode_google(body.home_address, _google_key)
        if coords is None:
            # No Google key configured, or Google returned no results — try Nominatim
            coords = await _geocode_nominatim(body.home_address)
        if coords is None:
            raise HTTPException(
                status_code=422, detail=f"Could not find location: {body.home_address!r}"
            )
        home_lat, home_lon = coords
    except HTTPException:
        raise
    except Exception as _exc:
        logger.warning("Geocoding failed: %s", _exc)
        raise HTTPException(
            status_code=422,
            detail="Could not geocode address — check your internet connection and try again",
        )

    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True

    profile_data = {
        "user": {
            "name": body.name,
            "home_address": body.home_address,
            "home_coordinates": [home_lat, home_lon],
            "fitness_level": body.fitness_level,
            "dietary_restrictions": body.dietary_restrictions,
            "preferred_activities": body.preferred_activities,
            "max_driving_minutes": body.max_driving_minutes,
        },
        "family": {"members": []},
        "models": {"local_model": "qwen3.5:9b"},
        "planning": {
            "max_iterations": body.max_iterations,
            "precipitation_threshold_pct": body.precipitation_threshold_pct,
            "aqi_threshold": body.aqi_threshold,
            "min_sunset_buffer_minutes": body.min_sunset_buffer_minutes,
            "cell_coverage_road_proximity_miles": body.cell_coverage_road_proximity_miles,
            "require_teen_cell_service": body.require_teen_cell_service,
            "earliest_departure_hour": body.earliest_departure_hour,
            "max_day_hours": body.max_day_hours,
            "restaurant_search_radius_miles": body.restaurant_search_radius_miles,
            "marginal_weather_precip_pct": body.marginal_weather_precip_pct,
            "hospital_search_radius_miles": body.hospital_search_radius_miles,
            "max_candidate_activities": body.max_candidate_activities,
            "include_meal": body.include_meal,
        },
    }

    config.paths.base_dir.mkdir(parents=True, exist_ok=True)
    profile_path = config.paths.base_dir / "profile.yaml"

    import io

    stream = io.StringIO()
    yaml.dump(profile_data, stream)
    profile_path.write_text(stream.getvalue(), encoding="utf-8")

    # Reload config from disk so all subsequent requests use the saved profile
    # (the server starts with defaults when profile.yaml doesn't exist yet).
    try:
        request.app.state.config = NexusConfig.load(profile_path)
    except Exception as _reload_exc:
        logger.warning("Config reload after setup failed: %s", _reload_exc)

    return {"status": "profile_saved", "path": str(profile_path)}


@router.post("/api/setup/api-keys")
async def save_api_keys(request: Request, body: ApiKeyRequest) -> dict:
    """Save API keys to ~/.nexus/.env (never to profile.yaml)."""
    config = _get_config(request)
    env_path = config.paths.base_dir / ".env"
    lines: list[str] = []

    if env_path.exists():
        existing = env_path.read_text(encoding="utf-8").splitlines()
        lines = [ln for ln in existing if not ln.startswith("GOOGLE_PLACES_API_KEY=")]

    if body.google_places_api_key:
        lines.append(f"GOOGLE_PLACES_API_KEY={body.google_places_api_key}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env_path.chmod(0o600)  # Read-only by owner only

    return {"status": "api_keys_saved"}


@router.get("/api/setup/api-keys/status", response_model=ApiKeyStatus)
async def api_key_status(request: Request) -> ApiKeyStatus:
    """Check which API keys are configured — reads .env directly so it reflects recent saves."""
    config = _get_config(request)
    env_path = config.paths.base_dir / ".env"
    places_key = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("GOOGLE_PLACES_API_KEY="):
                places_key = line.split("=", 1)[1].strip()
                break
    return ApiKeyStatus(
        places_configured=bool(places_key),
        places_key_prefix=places_key[:4] if places_key else None,
    )


@router.get("/api/preflight", response_model=PreflightStatus)
async def preflight_check(request: Request) -> PreflightStatus:
    """Check Ollama, model availability, and profile existence."""
    config = _get_config(request)
    issues: list[str] = []

    # Check Ollama running
    ollama_ok = await _check_ollama(config.ollama.base_url)
    if not ollama_ok:
        issues.append(f"Ollama not running at {config.ollama.base_url}")

    # Check model available
    model_ok = await _check_model(config.ollama.base_url, config.models.local_model)
    if not model_ok:
        issues.append(f"Model '{config.models.local_model}' not pulled in Ollama")

    # Check profile exists
    profile_path = config.paths.base_dir / "profile.yaml"
    profile_ok = profile_path.exists()
    if not profile_ok:
        issues.append("Profile not configured — visit /setup")

    return PreflightStatus(
        ollama_running=ollama_ok,
        model_available=model_ok,
        profile_exists=profile_ok,
        all_ok=not issues,
        issues=issues,
    )


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────────────────────────────────────


@router.websocket("/ws/plans/{request_id}")
async def websocket_plan_progress(websocket: WebSocket, request_id: str) -> None:
    """
    Stream planning progress events to the browser.

    • Attaches to the shared PlanningProgress registry for *request_id*.
    • Replays all events that completed before this connection arrived (Tech §9.7).
    • Accepts incoming messages of type "add_constraint" (task 6.7) and
      "stop_planning" (task 6.12).
    • Detaches cleanly on disconnect or error.
    """
    await websocket.accept()

    from nexus.web.progress import get_or_create

    progress = get_or_create(request_id)
    await progress.attach(websocket)

    try:
        while True:
            # Receive incoming messages (constraint injection, stop, heartbeat)
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                msg = json.loads(raw)

                if msg.get("type") == "add_constraint":
                    # Mid-flight constraint injection via WebSocket (task 6.7)
                    constraint_text = msg.get("text", "")
                    if constraint_text:
                        logger.info("WS constraint for %s: %s", request_id, constraint_text)
                        try:
                            from nexus.graph.planner import build_planning_graph

                            _cfg: NexusConfig = websocket.app.state.config
                            _cp_path = _cfg.paths.checkpoints_dir / "nexus.db"
                            async with _open_checkpointer(_cp_path) as _saver:
                                _graph = build_planning_graph(checkpointer=_saver)
                                _tc = {"configurable": {"thread_id": request_id}}
                                _state = await _graph.aget_state(_tc)
                                if _state.values:
                                    _existing = list(_state.values.get("pending_constraints", []))
                                    _existing.append(constraint_text)
                                    await _graph.aupdate_state(
                                        _tc, {"pending_constraints": _existing}
                                    )
                                    logger.info("WS constraint injected for %s", request_id)
                        except Exception as _exc:
                            logger.warning("WS add_constraint failed for %s: %s", request_id, _exc)

                elif msg.get("type") == "stop_planning":
                    # Cancel the active planning task (task 6.12)
                    task = _active_tasks.get(request_id)
                    if task and not task.done():
                        logger.info("stop_planning received for %s — cancelling task", request_id)
                        task.cancel()
                    # on_planning_error is emitted inside _run()'s CancelledError handler

            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

    except Exception as exc:
        logger.warning("WebSocket error for %s: %s", request_id, exc)
        try:
            await websocket.send_text(json.dumps({"event": "error", "message": str(exc)}))
        except Exception:
            pass
    finally:
        progress.detach(websocket)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _html_page(request: Request, template: str, context: dict | None = None) -> HTMLResponse:
    """Render an HTML page via Jinja2 templates (Phase 7)."""
    from nexus.output.html import render_page

    # Map template filename to Jinja2 template name (.html → .html.j2)
    j2_name = template.replace(".html", ".html.j2")

    ctx = context or {}
    try:
        content = render_page(j2_name, **ctx)
    except Exception as exc:
        logger.error("Template render error for %s: %s", j2_name, exc)
        content = f"<h1>Nexus</h1><p>Template error: {exc}</p>"

    return HTMLResponse(content=content)


def _new_request_id() -> str:
    import uuid

    return str(uuid.uuid4())


async def _check_ollama(base_url: str) -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def _check_model(base_url: str, model_name: str) -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(model_name in m for m in models)
    except Exception:
        return False
