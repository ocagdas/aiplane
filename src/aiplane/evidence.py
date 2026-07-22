from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping


EVIDENCE_SCHEMA_VERSION = "1.0"
EVIDENCE_STATES = frozenset({"configured", "detected", "discovered", "generated", "measured", "unresolved"})


def evidence_source(
    name: str,
    state: str,
    source: str | None,
    *,
    value: Any = None,
    sample_count: int | None = None,
    **details: Any,
) -> dict[str, Any]:
    if state not in EVIDENCE_STATES:
        allowed = ", ".join(sorted(EVIDENCE_STATES))
        raise ValueError(f"unknown evidence state {state!r}; expected one of: {allowed}")
    row: dict[str, Any] = {"name": name, "state": state, "source": source}
    if value is not None:
        row["value"] = value
    if sample_count is not None:
        if sample_count < 0:
            raise ValueError("sample_count cannot be negative")
        row["sample_count"] = sample_count
    row.update({key: value for key, value in details.items() if value is not None})
    return row


def evidence_provenance(
    sources: Iterable[Mapping[str, Any]],
    *,
    uncertainty: Iterable[str] = (),
    sample_count: int | None = None,
    method: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    rows = [dict(row) for row in sources]
    for row in rows:
        state = str(row.get("state") or "")
        if state not in EVIDENCE_STATES:
            raise ValueError(f"evidence source {row.get('name', '<unnamed>')!r} has unknown state {state!r}")
    uncertainty_items = list(dict.fromkeys(str(item) for item in uncertainty if str(item).strip()))
    counts = Counter(str(row["state"]) for row in rows)
    if sample_count is None:
        sample_count = sum(int(row.get("sample_count", 0) or 0) for row in rows if row["state"] == "measured")
    if sample_count < 0:
        raise ValueError("sample_count cannot be negative")
    useful_sources = len(rows) - counts["unresolved"]
    if useful_sources == 0:
        evidence_state = "unresolved"
    elif uncertainty_items or counts["unresolved"]:
        evidence_state = "partial"
    else:
        evidence_state = "complete"
    summary = {f"{state}_values": counts[state] for state in sorted(EVIDENCE_STATES)}
    # Kept for pre-1.0 discover consumers while "configured" is the canonical state.
    summary["user_supplied_values"] = counts["configured"]
    payload: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "evidence_state": evidence_state,
        "sample_count": sample_count,
        "sources": rows,
        "uncertainty": uncertainty_items,
        "summary": summary,
    }
    if method:
        payload["method"] = method
    payload.update(details)
    return payload
