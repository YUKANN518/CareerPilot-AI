"""Source name normalization for job discovery platforms.

JobsDB and OfferToday are displayed as discovery entry points. The database
may store source names in different cases (for example ``JobsDB`` or
``offertoday``). The API layer always emits the canonical upper-case names so
frontend filters and badges stay consistent.
"""

from __future__ import annotations

# Canonical discovery platform names returned by the API.
JOBSDB_CANONICAL = "JOBSDB"
OFFERTODAY_CANONICAL = "OFFERTODAY"

# Known aliases that map to each canonical name. Matching is case-insensitive
# against the stripped source name.
_JOBSDB_ALIASES = frozenset({"jobsdb", "jobsdb · 香港公开岗位快照"})
_OFFERTODAY_ALIASES = frozenset({"offertoday", "offertoday · 香港公开岗位快照"})

# Hosts that identify each platform on the public web.
JOBSDB_HOSTS = frozenset({"jobsdb.com", "hk.jobsdb.com", "sg.jobsdb.com"})
OFFERTODAY_HOSTS = frozenset({"offertoday.com", "m.offertoday.com"})


def canonical_source_name(source_name: str | None) -> str | None:
    """Return the canonical upper-case name for a known discovery platform.

    For unknown sources the input is returned untouched so admin-configured
    sources keep their original display name.
    """
    if not source_name:
        return source_name
    normalized = source_name.strip().casefold()
    if normalized in _JOBSDB_ALIASES or normalized == JOBSDB_CANONICAL.casefold():
        return JOBSDB_CANONICAL
    if normalized in _OFFERTODAY_ALIASES or normalized == OFFERTODAY_CANONICAL.casefold():
        return OFFERTODAY_CANONICAL
    return source_name


def is_discovery_platform(source_name: str | None) -> bool:
    """True when the source is JobsDB or OfferToday (any case)."""
    if not source_name:
        return False
    normalized = source_name.strip().casefold()
    return normalized in _JOBSDB_ALIASES or normalized in _OFFERTODAY_ALIASES


def is_jobsdb(source_name: str | None) -> bool:
    if not source_name:
        return False
    return source_name.strip().casefold() in _JOBSDB_ALIASES


def is_offertoday(source_name: str | None) -> bool:
    if not source_name:
        return False
    return source_name.strip().casefold() in _OFFERTODAY_ALIASES


def canonical_name_for_host(host: str | None) -> str | None:
    """Map a URL host to a canonical platform name, if recognised."""
    if not host:
        return None
    normalized = host.strip().casefold().rstrip(".")
    if normalized in JOBSDB_HOSTS or normalized.endswith(".jobsdb.com"):
        return JOBSDB_CANONICAL
    if normalized in OFFERTODAY_HOSTS or normalized.endswith(".offertoday.com"):
        return OFFERTODAY_CANONICAL
    return None
