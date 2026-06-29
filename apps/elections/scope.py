"""College-scope helpers for voter-facing ballot and tally rules."""
from __future__ import annotations

import re
from typing import Iterable

from apps.elections.constants import OFFICIAL_COLLEGES


HOUSE_COLLEGE_CATEGORY = "house_college"
CAMPUS_ELECTION_TYPE = "campus"
COLLEGE_ELECTION_TYPE = "college"

_DASH_RE = re.compile(r"[\u2010-\u2015\u002D\uFE58\uFE63\uFF0D]+")
_LEADING_SCOPE_RE = re.compile(r"^[\s\-\u2010-\u2015\uFE58\uFE63\uFF0D\uFFFD]+")
_TITLE_SEPARATORS = (
    " - ",
    "\u2013",
    "\u2014",
    "\u00e2\u20ac\u201c",
    "\u00e2\u20ac\u0093",
    "\ufffd",
)


def normalize_college(name: str | None) -> str:
    """
    Return a stable comparison key for college names.

    The stored data usually uses full official names, but user-entered imports
    and older position titles can vary by case, dash style, or the leading
    "College of" phrase.
    """
    value = (name or "").strip().lower()
    value = _DASH_RE.sub("-", value)
    value = re.sub(r"\s+", " ", value)
    if value.startswith("college of "):
        value = value[len("college of "):]
    return value.strip()


def college_matches(left: str | None, right: str | None) -> bool:
    """Return True when both college names resolve to the same non-empty key."""
    left_key = normalize_college(left)
    right_key = normalize_college(right)
    return bool(left_key and right_key and left_key == right_key)


def resolve_official_college(name: str | None) -> str:
    """
    Resolve a full or short college name to the official display name when known.
    """
    raw = (name or "").strip()
    if not raw:
        return ""

    raw_key = normalize_college(raw)
    for official in OFFICIAL_COLLEGES:
        if raw_key == normalize_college(official):
            return official
    return raw


def extract_college_from_position_title(title: str | None) -> str:
    """
    Extract the represented college from a legacy College Representative title.
    """
    value = (title or "").strip()
    if not value:
        return ""

    prefix = "College Representative"
    rest = ""
    if value.lower().startswith(prefix.lower()):
        rest = value[len(prefix):].strip()
    else:
        for separator in _TITLE_SEPARATORS:
            if separator in value:
                rest = value.split(separator, 1)[1].strip()
                break

    if not rest:
        for separator in _TITLE_SEPARATORS:
            if separator in value:
                rest = value.split(separator, 1)[1].strip()
                break

    rest = _LEADING_SCOPE_RE.sub("", rest).strip()
    return resolve_official_college(rest)


def is_campus_college_rep_position(election, position) -> bool:
    """Return True for campus-wide House College Representative seats."""
    return (
        getattr(election, "election_type", "") == CAMPUS_ELECTION_TYPE
        and getattr(position, "category", "") == HOUSE_COLLEGE_CATEGORY
    )


def resolve_position_scope_college(position, candidate_colleges: Iterable[str] | None = None) -> str:
    """
    Resolve the represented college for a campus college-rep position.

    New records store this in ``Position.scope_college``. Older records are
    resolved from the position title first, then from candidate college data.
    """
    explicit = (getattr(position, "scope_college", "") or "").strip()
    if explicit:
        return resolve_official_college(explicit)

    from_title = extract_college_from_position_title(getattr(position, "title", ""))
    if from_title:
        return from_title

    colleges = {
        resolve_official_college(college)
        for college in (candidate_colleges or [])
        if (college or "").strip()
    }
    colleges = {college for college in colleges if college}
    if len(colleges) == 1:
        return next(iter(colleges))
    return ""


def election_matches_voter_college(election, voter_college: str | None) -> bool:
    """Return True when the voter is in scope for the election itself."""
    if getattr(election, "election_type", "") == COLLEGE_ELECTION_TYPE:
        return college_matches(getattr(election, "college", ""), voter_college)
    return True


def position_visible_to_voter(election, position, voter_college: str | None) -> bool:
    """Return True if the voter should see this position on the ballot."""
    if not election_matches_voter_college(election, voter_college):
        return False

    if is_campus_college_rep_position(election, position):
        return college_matches(resolve_position_scope_college(position), voter_college)

    return True


def candidate_selectable_by_voter(election, position, candidate, voter_college: str | None) -> bool:
    """Return True if the voter may select this candidate for this position."""
    if not position_visible_to_voter(election, position, voter_college):
        return False

    if is_campus_college_rep_position(election, position):
        position_college = resolve_position_scope_college(position)
        candidate_college = getattr(candidate, "college", "") or ""
        return (
            college_matches(candidate_college, voter_college)
            and college_matches(candidate_college, position_college)
        )

    return True


def filter_candidates_for_voter(election, position, candidates, voter_college: str | None) -> list:
    """Return only candidates selectable by the voter."""
    return [
        candidate
        for candidate in candidates
        if candidate_selectable_by_voter(election, position, candidate, voter_college)
    ]
