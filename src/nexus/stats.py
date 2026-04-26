"""
Usage statistics tracker — UX §9.4.

SQLite table at ~/.nexus/stats.db (stdlib sqlite3 — no ORM).
Records plan lifecycle events for the history page stats card.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _connect(stats_db: Path) -> sqlite3.Connection:
    stats_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(stats_db))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plan_stats (
            request_id    TEXT PRIMARY KEY,
            planned_at    TEXT NOT NULL,
            approved_at   TEXT,
            activity_type TEXT,
            approved      INTEGER DEFAULT 0,
            approval_pass INTEGER DEFAULT 0,
            trust_score   INTEGER,
            feedback_given INTEGER DEFAULT 0
        )
    """)
    # Migrate older DBs that lack new columns (idempotent)
    try:
        conn.execute("ALTER TABLE plan_stats ADD COLUMN approved_at TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE plan_stats ADD COLUMN trust_score INTEGER")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE plan_stats ADD COLUMN feedback_given INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn


def record_plan_started(stats_db: Path, request_id: str, activity_type: str | None = None) -> None:
    """Record that a new planning run has started."""
    with _connect(stats_db) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO plan_stats (request_id, planned_at, activity_type)
            VALUES (?, ?, ?)
            """,
            (request_id, datetime.now(tz=timezone.utc).isoformat(), activity_type),
        )


def record_plan_approved(stats_db: Path, request_id: str, pass_number: int = 1) -> None:
    """Record that a plan was approved (pass_number = 1 for first-pass approval)."""
    with _connect(stats_db) as conn:
        conn.execute(
            """
            UPDATE plan_stats
            SET approved = 1, approval_pass = ?, approved_at = ?
            WHERE request_id = ?
            """,
            (pass_number, datetime.now(tz=timezone.utc).isoformat(), request_id),
        )


def record_trust_score(stats_db: Path, request_id: str, score: int) -> None:
    """Record user trust score (1–5) for an approved plan (PRD §12.1)."""
    if not 1 <= score <= 5:
        raise ValueError(f"Trust score must be 1–5, got {score}")
    with _connect(stats_db) as conn:
        conn.execute(
            "UPDATE plan_stats SET trust_score = ? WHERE request_id = ?",
            (score, request_id),
        )


def record_feedback_given(stats_db: Path, request_id: str) -> None:
    """Mark that post-trip feedback was appended to the plan file."""
    with _connect(stats_db) as conn:
        conn.execute(
            "UPDATE plan_stats SET feedback_given = 1 WHERE request_id = ?",
            (request_id,),
        )


def get_ux_metrics_summary(stats_db: Path) -> dict:
    """
    Aggregate UX §15.1 metrics for --debug reporting.

    Returns:
        approval_time_avg_seconds: average seconds from started → approved
        first_pass_rate: fraction of plans approved on first pass
        avg_trust_score: mean trust score (1–5) across rated plans
        feedback_completion_rate: fraction of approved plans with post-trip feedback
    """
    if not stats_db.exists():
        return {}
    with _connect(stats_db) as conn:
        rows = conn.execute(
            """
            SELECT planned_at, approved_at, approval_pass, trust_score, feedback_given
            FROM plan_stats
            WHERE approved = 1
            """
        ).fetchall()

    if not rows:
        return {"approved_plans": 0}

    import statistics

    approval_times = []
    for r in rows:
        if r["planned_at"] and r["approved_at"]:
            try:
                start = datetime.fromisoformat(r["planned_at"])
                end = datetime.fromisoformat(r["approved_at"])
                approval_times.append((end - start).total_seconds())
            except ValueError:
                pass

    trust_scores = [r["trust_score"] for r in rows if r["trust_score"] is not None]
    first_pass = [r for r in rows if r["approval_pass"] == 1]
    feedback_given = [r for r in rows if r["feedback_given"]]

    return {
        "approved_plans": len(rows),
        "approval_time_avg_seconds": round(statistics.mean(approval_times), 1)
        if approval_times
        else None,
        "first_pass_rate": round(len(first_pass) / len(rows), 3),
        "avg_trust_score": round(statistics.mean(trust_scores), 2) if trust_scores else None,
        "feedback_completion_rate": round(len(feedback_given) / len(rows), 3),
    }


def record_plan_rejected(stats_db: Path, request_id: str) -> None:
    """Record a human rejection event (increments approval pass tracking implicitly)."""
    with _connect(stats_db) as conn:
        conn.execute(
            """
            UPDATE plan_stats
            SET approved = 0
            WHERE request_id = ?
            """,
            (request_id,),
        )


def get_monthly_stats(stats_db: Path) -> dict:
    """
    Return current calendar-month stats for the landing page card (task 6.18).

    Returns: {"plans_this_month": int, "first_pass_approval_rate": float | None}
    Empty month returns {"plans_this_month": 0, "first_pass_approval_rate": None}.
    """
    from datetime import date

    month_prefix = date.today().strftime("%Y-%m")
    if not stats_db.exists():
        return {"plans_this_month": 0, "first_pass_approval_rate": None}

    with _connect(stats_db) as conn:
        rows = conn.execute(
            "SELECT approved, approval_pass FROM plan_stats WHERE planned_at LIKE ?",
            (f"{month_prefix}%",),
        ).fetchall()

    if not rows:
        return {"plans_this_month": 0, "first_pass_approval_rate": None}

    approved = [r for r in rows if r["approved"]]
    first_pass = [r for r in approved if r["approval_pass"] == 1]
    rate: float | None = round(len(first_pass) / len(approved), 3) if approved else None
    return {"plans_this_month": len(rows), "first_pass_approval_rate": rate}


def get_summary(stats_db: Path) -> dict:
    """Return summary stats for the landing page history card."""
    if not stats_db.exists():
        return {"total_plans": 0, "approved_plans": 0, "approval_rate": 0.0}
    with _connect(stats_db) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, SUM(approved) AS approved_count FROM plan_stats"
        ).fetchone()
    total = row["total"] or 0
    approved = row["approved_count"] or 0
    return {
        "total_plans": total,
        "approved_plans": approved,
        "approval_rate": round(approved / total * 100, 1) if total else 0.0,
    }


def get_recent_plans(stats_db: Path, limit: int = 5) -> list[dict]:
    """Return the most recent plans for the landing page list."""
    if not stats_db.exists():
        return []
    with _connect(stats_db) as conn:
        rows = conn.execute(
            """
            SELECT request_id, activity_type, planned_at, approved, feedback_given
            FROM plan_stats
            ORDER BY planned_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    result = []
    for r in rows:
        planned_at = r["planned_at"] or ""
        try:
            date_label = datetime.fromisoformat(planned_at).strftime("%b %d, %Y")
        except ValueError:
            date_label = planned_at[:10]
        result.append(
            {
                "request_id": r["request_id"],
                "activity": r["activity_type"] or "Weekend plan",
                "date": date_label,
                "approved": bool(r["approved"]),
                "has_feedback": bool(r["feedback_given"]),
            }
        )
    return result
