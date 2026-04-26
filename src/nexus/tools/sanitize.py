"""
Tool output sanitization — ISSUE-16.

Prevents prompt-injection attacks by stripping instruction-like patterns
from untrusted tool-return text (OSM descriptions, Google Places summaries,
restaurant names, etc.) before that text is embedded in LLM prompts.

Design constraints:
  - Deterministic and fast (no LLM call).
  - Zero false-positives on legitimate place names like "Follow the Creek Trail".
  - Matched text replaced with "[Content removed]" so the LLM knows data was
    redacted rather than seeing an unexpected blank.
  - An ActivityResult whose *name* triggers the pattern is dropped entirely
    (a named activity is the primary key; a bad name poisons all downstream
    reasoning more severely than a bad description).
"""

from __future__ import annotations

import re

# Patterns that unambiguously signal prompt-injection attempts.
# Kept deliberately narrow to avoid false positives on trail descriptions.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # "Ignore previous instructions", "Disregard the above", etc.
    re.compile(
        r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|above|prior|earlier)"
        r"(?:\s+instructions?)?\b",
        re.IGNORECASE,
    ),
    # "You are now a …", "Act as …", "Pretend you are …"
    re.compile(
        r"\b(?:you\s+are\s+now|act\s+as|pretend\s+(?:you\s+are|to\s+be)|roleplay\s+as)\b",
        re.IGNORECASE,
    ),
    # Jailbreak framing: "DAN mode", "developer mode enabled"
    re.compile(r"\b(?:DAN\s+mode|developer\s+mode\s+enabled|jailbreak)\b", re.IGNORECASE),
    # Explicit instruction injection signals
    re.compile(r"\bSYSTEM\s*:\s*", re.IGNORECASE),
    re.compile(r"\bINSTRUCTION\s*:\s*", re.IGNORECASE),
    # "Do not follow", "Do not comply with"
    re.compile(r"\bdo\s+not\s+(?:follow|comply\s+with|obey)\b", re.IGNORECASE),
]

# For *names*: only flag direct command-style tokens (much narrower)
_NAME_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|above|prior|earlier)"
        r"(?:\s+instructions?)?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bSYSTEM\s*:\s*", re.IGNORECASE),
    re.compile(r"\bINSTRUCTION\s*:\s*", re.IGNORECASE),
]


def _contains_injection(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def sanitize_tool_text(text: str) -> str:
    """Sanitize a free-text field from tool output.

    If the text matches an injection pattern, returns "[Content removed]".
    Otherwise returns the original string unchanged.
    """
    if not text:
        return text
    if _contains_injection(text, _INJECTION_PATTERNS):
        return "[Content removed]"
    return text


def sanitize_activity_name(name: str) -> str | None:
    """Sanitize an activity name.

    Returns None if the name matches an injection pattern — callers must
    drop the ActivityResult entirely in that case.
    Returns the original name if clean.
    """
    if not name:
        return name
    if _contains_injection(name, _NAME_INJECTION_PATTERNS):
        return None
    return name
