"""Shared anti-fabrication validation utilities.

These pure functions are used by evidence-grounded generation features to
ensure generated content does not
introduce unevidenced skills or unsubstantiated numbers.

The functions are intentionally framework-agnostic and side-effect free
so they can be unit-tested in isolation and reused by any service that
needs fact-based validation.
"""

from __future__ import annotations

import re

# Separators: spaces, hyphens, slashes, backslashes, CN/EN punctuation.
SKILL_SEPARATOR_RE = re.compile(r"[\s\-/\\,.;:!?()\[\]\"'`，。；：！？（）、，]+")  # noqa: RUF001

# Number facts: percentages, currency, headcount, multiples, durations, quantities.
# Multi-character units (个月、小时、分钟、美元 etc.) must precede single-char
# ones so ``3个月`` is not truncated to ``3个``. A unit is required — a bare
# number (e.g. ``2`` in ``E2E``) is not a verifiable numeric fact.
NUMBER_PHRASE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:个月|小时|分钟|美元|%|元|万|亿|人|个|次|项|倍|年|月|天|秒"
    r"|qps|rps|tps|ms|gb|mb|tb|x)",
    re.IGNORECASE,
)


def normalize_skill_tokens(name: str) -> list[str]:
    """Normalize a skill name into a lowercase token list.

    Splits on spaces, hyphens, slashes and CN/EN punctuation, discarding
    empty tokens. Examples:

    * ``"Docker Compose"`` → ``["docker", "compose"]``
    * ``"CI/CD"`` → ``["ci", "cd"]``
    * ``"TypeScript"`` → ``["typescript"]``
    """
    lowered = name.lower()
    return [token for token in SKILL_SEPARATOR_RE.split(lowered) if token]


def skill_mentioned(skill_name: str, text: str) -> bool:
    """Check whether ``skill_name`` is mentioned in ``text``.

    Both the skill name and the text are normalized into lowercase token
    sequences. The skill's tokens must appear as a **contiguous
    subsequence** in the text tokens. This ensures:

    * Missing skill ``Docker`` matches text containing ``Docker Compose``
      (``["docker"]`` is a prefix of ``["docker", "compose"]``).
    * Missing skill ``Docker Compose`` does **not** match text that only
      contains ``Docker`` (requires ``["docker", "compose"]`` contiguous).
    * ``CI/CD`` matches ``"CI/CD pipeline"`` (tokens ``ci cd`` contiguous).
    * ``TypeScript`` does **not** match ``"Type Script"`` (different tokens).
    """
    skill_tokens = normalize_skill_tokens(skill_name)
    if not skill_tokens:
        return False
    text_tokens = normalize_skill_tokens(text)
    if not text_tokens:
        return False
    n = len(skill_tokens)
    return any(text_tokens[i : i + n] == skill_tokens for i in range(len(text_tokens) - n + 1))


def extract_number_phrases(text: str) -> set[str]:
    """Extract normalized numeric fact phrases from ``text``.

    Returns a set of lowercase, space-stripped ``number + unit`` strings.
    For example ``"提升 80%"`` → ``{"80%"}``, ``"支持 1.2 万 QPS"`` →
    ``{"1.2万qps"}``. Used to check whether numbers in edited content
    already exist in the original text or evidence text.
    """
    return {m.group(0).lower().replace(" ", "") for m in NUMBER_PHRASE_RE.finditer(text or "")}


def assert_no_missing_skills(
    text: str,
    missing_skills: list[str],
) -> list[str]:
    """Return the list of missing skills found in ``text``.

    For each skill name in ``missing_skills``, if ``skill_mentioned``
    returns True, the skill is considered introduced in the text. The
    caller decides how to handle the returned list (typically: non-empty
    → rejection with a 422 error).
    """
    introduced: list[str] = []
    for skill_name in missing_skills:
        if skill_mentioned(skill_name, text):
            introduced.append(skill_name)
    return introduced


def find_unsubstantiated_numbers(
    text: str,
    *allowed_sources: str,
) -> set[str]:
    """Return numbers in ``text`` that are not present in any allowed source.

    ``allowed_sources`` are one or more text strings (original text,
    evidence text, etc.) whose numbers form the allowed set. Numbers in
    ``text`` that do not appear in the union of allowed sources are
    returned as unsubstantiated.
    """
    allowed: set[str] = set()
    for source in allowed_sources:
        allowed |= extract_number_phrases(source)
    text_numbers = extract_number_phrases(text)
    return text_numbers - allowed
