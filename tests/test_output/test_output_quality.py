"""
Phase 10B — Output Quality Verification tests (tasks 10.6–10.8).

10.6  No system internals leak into user-facing output (UX §1.3, PRD §9.4).
10.7  Copy rules respected: no emoji, no "Sorry", no first-person "I", no
      "the system" in templates and progress messages (UX §10.1–10.3).
10.8  Plan content completeness: every approved plan has all 9 required
      elements (PRD §9.5).

The template checks are static (grep the source files); the completeness
checks use the HTML snapshot produced by test_html_render.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "src" / "nexus" / "templates"
SNAPSHOT_PATH = Path(__file__).parent.parent / "fixtures" / "plan_snapshot.html"

# ── 10.6 — No system internals in templates ────────────────────────────────


class TestNoSystemInternalsLeaked:
    """UX §1.3, PRD §9.4 — Hard requirement: zero internal architecture terms
    may appear in user-facing template output."""

    # Terms that must never appear in user-visible HTML/Markdown templates
    BANNED_TERMS = [
        "APPROVED",
        "REJECTED",
        "NEEDS_INFO",
        "LangGraph",
        "meteorology",
        "logistics",
        "nutritional",
        "family_coordinator",
        "orchestrator",
        "synthesizer",
        "parse_intent",
        "draft_proposal",
        "check_consensus",
        "save_plan",
        "agent_name",
        "node_name",
        "iteration_count",
        "negotiation_log",
    ]

    def _template_files(self) -> list[Path]:
        # Only check user-facing output templates — the planning.html.j2 progress
        # page intentionally contains node/agent names for the developer trace panel.
        USER_FACING = {"plan.html.j2", "history.html.j2", "base.html.j2", "index.html.j2"}
        return [f for f in TEMPLATES_DIR.glob("*.j2") if f.name in USER_FACING]

    def _jinja_comment_stripped(self, text: str) -> str:
        """Remove Jinja2 comments ({# ... #}) before checking."""
        return re.sub(r"\{#.*?#\}", "", text, flags=re.DOTALL)

    @pytest.mark.parametrize("term", BANNED_TERMS)
    def test_term_not_in_template_content(self, term: str) -> None:
        """Banned term must not appear as literal content in any user-facing template."""
        violations: list[str] = []
        for tmpl in self._template_files():
            source = self._jinja_comment_stripped(tmpl.read_text())
            # Only check lines that are NOT pure Jinja2 variable expressions or
            # control blocks — we care about text that is rendered to the user.
            for i, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                # Skip lines that are pure Jinja2 blocks (e.g. {% if ... %})
                if stripped.startswith("{%") or stripped.startswith("{#"):
                    continue
                # Check for the term in rendered text segments
                # (outside of {{ ... }} expressions)
                rendered_text = re.sub(r"\{\{.*?\}\}", "", line)
                if term in rendered_text:
                    violations.append(f"{tmpl.name}:{i}: {line.rstrip()}")

        assert violations == [], (
            f"Banned term '{term}' found in template(s):\n" + "\n".join(violations)
        )

    def test_progress_messages_contain_no_agent_names(self) -> None:
        """messages.py must not expose any agent or node name to users."""
        from nexus.web.messages import NODE_MESSAGES, ITERATION_NODE_MESSAGES

        agent_names = {
            "meteorology",
            "logistics",
            "nutritional",
            "family_coordinator",
            "orchestrator",
            "synthesizer",
            "parse_intent",
            "draft_proposal",
            "check_consensus",
            "save_plan",
        }

        all_messages = list(NODE_MESSAGES.values()) + list(ITERATION_NODE_MESSAGES.values())
        for msg in all_messages:
            for name in agent_names:
                assert name not in msg.lower(), (
                    f"Progress message exposes agent name '{name}': {msg!r}"
                )

    def test_progress_messages_contain_no_verdict_terms(self) -> None:
        from nexus.web.messages import NODE_MESSAGES, ITERATION_NODE_MESSAGES

        banned_in_messages = ["APPROVED", "REJECTED", "NEEDS_INFO", "iteration_count"]
        all_messages = list(NODE_MESSAGES.values()) + list(ITERATION_NODE_MESSAGES.values())
        for msg in all_messages:
            for term in banned_in_messages:
                assert term not in msg, (
                    f"Progress message contains banned term '{term}': {msg!r}"
                )


# ── 10.7 — Copy rules ──────────────────────────────────────────────────────


class TestCopyRules:
    """UX §10.1–10.3 — Voice and tone constraints."""

    EMOJI_PATTERN = re.compile(
        "[\U00010000-\U0010ffff]",  # Supplementary Multilingual Plane (emoji)
        flags=re.UNICODE,
    )

    def _all_template_text(self) -> str:
        texts = []
        for f in TEMPLATES_DIR.glob("*.j2"):
            texts.append(f.read_text())
        return "\n".join(texts)

    def _all_progress_messages(self) -> list[str]:
        from nexus.web.messages import NODE_MESSAGES, ITERATION_NODE_MESSAGES

        return list(NODE_MESSAGES.values()) + list(ITERATION_NODE_MESSAGES.values())

    def test_no_emoji_in_progress_messages(self) -> None:
        """Progress messages must never contain emoji (UX §10.2)."""
        for msg in self._all_progress_messages():
            assert not self.EMOJI_PATTERN.search(msg), f"Emoji found in message: {msg!r}"

    def test_no_sorry_in_progress_messages(self) -> None:
        """'Sorry' is banned from all user-facing progress text (UX §10.1)."""
        for msg in self._all_progress_messages():
            assert "sorry" not in msg.lower(), f"'Sorry' found in message: {msg!r}"

    def test_no_first_person_i_in_progress_messages(self) -> None:
        """Progress messages must not use first-person 'I' (UX §10.1)."""
        first_person_pattern = re.compile(r"\bI\b")
        for msg in self._all_progress_messages():
            assert not first_person_pattern.search(msg), (
                f"First-person 'I' found in message: {msg!r}"
            )

    def test_no_the_system_in_templates(self) -> None:
        """'The system' is a banned phrase (UX §10.1)."""
        text = self._all_template_text()
        # Strip Jinja2 control blocks before checking
        rendered = re.sub(r"\{%.*?%\}", "", text, flags=re.DOTALL)
        rendered = re.sub(r"\{\{.*?\}\}", "", rendered, flags=re.DOTALL)
        assert "the system" not in rendered.lower(), (
            "'the system' phrase found in a template — use active voice instead."
        )

    def test_progress_messages_are_concise(self) -> None:
        """Progress lines should be ≤ ~80 chars (UX §10.3)."""
        too_long = [
            msg for msg in self._all_progress_messages() if len(msg) > 80
        ]
        assert not too_long, (
            "Progress message(s) exceed 80 chars:\n"
            + "\n".join(f"  {m!r} ({len(m)} chars)" for m in too_long)
        )


# ── 10.8 — Plan content completeness ───────────────────────────────────────


class TestPlanContentCompleteness:
    """PRD §9.5 — Every approved plan must include all 9 required elements."""

    @pytest.fixture
    def snapshot_html(self) -> str:
        """Return the committed plan snapshot HTML for structural checks."""
        if not SNAPSHOT_PATH.exists():
            pytest.skip("Plan snapshot not found — run test_html_render.py first to generate it")
        return SNAPSHOT_PATH.read_text(encoding="utf-8")

    # The 9 required elements (PRD §9.5) mapped to markers that are
    # unconditionally rendered in the snapshot (i.e. always present when
    # the fixture supplies all required non-optional fields).
    # Conditional sections (backup, tradeoff) are verified via the template
    # source check in test_plan_template_has_all_required_sections below.
    REQUIRED_ELEMENTS = {
        "activity_stats_bar": "stats-bar",
        "conditions_verdict": "verdict-strip",
        "why_this_plan_section": "Why this plan",
        "full_day_timeline": "timeline",
        "preparation_checklist": "Before you go",
        "emergency_info": "Emergency",
        "decision_buttons": "btn-approve",
    }

    @pytest.mark.parametrize("element,marker", REQUIRED_ELEMENTS.items())
    def test_required_element_present_in_snapshot(self, snapshot_html: str, element: str, marker: str) -> None:
        """Each of the 9 required plan elements must be present in the snapshot."""
        assert marker in snapshot_html, (
            f"Required plan element '{element}' (marker: '{marker}') "
            f"is missing from plan_snapshot.html"
        )

    def test_plan_template_has_all_required_sections(self) -> None:
        """Verify the plan.html.j2 source includes all 9 structural sections."""
        template_src = (TEMPLATES_DIR / "plan.html.j2").read_text()

        # Check that the template source contains the structural sections
        required_in_source = [
            "stats-bar",
            "verdict-strip",
            "why_this_plan",
            "tradeoff_summary",
            "timeline",
            "backup_activity",
            "preparation_checklist",
            "emergency_info",
            "btn-approve",
        ]
        missing = [s for s in required_in_source if s not in template_src]
        assert missing == [], (
            f"Plan template missing structural elements: {missing}"
        )

    def test_markdown_template_has_frontmatter(self) -> None:
        """plan.md.j2 must include YAML frontmatter (Tech §9.6)."""
        md_tmpl = (TEMPLATES_DIR / "plan.md.j2").read_text()
        assert md_tmpl.startswith("---") or "date:" in md_tmpl[:200], (
            "plan.md.j2 is missing YAML frontmatter (date, activity, status, request_id)"
        )
