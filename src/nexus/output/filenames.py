"""
Plan filename generator — Tech §9.6.

Format: {date.isoformat()}-{slug}.md
"""

from __future__ import annotations

import re
from datetime import date


def plan_filename(activity_name: str, target_date: date) -> str:
    """
    Generate a safe filename for a saved plan.

    Example: "2026-04-19-windy-hill-preserve.md"
    """
    slug = _slugify(activity_name)
    return f"{target_date.isoformat()}-{slug}.md"


def _slugify(text: str, max_length: int = 30) -> str:
    """Convert activity name to URL/filename-safe slug."""
    # Lowercase
    slug = text.lower()
    # Remove special chars, keep alphanumeric and spaces
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    # Replace spaces with hyphens
    slug = re.sub(r"\s+", "-", slug.strip())
    # Remove consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Truncate
    return slug[:max_length].rstrip("-")
