from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from .models import Profile
from .persistence import atomic_update_json

_DURATION = re.compile(r"^(?P<value>[1-9][0-9]*)(?P<unit>[mhd])$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_duration(value: str) -> timedelta:
    match = _DURATION.fullmatch(str(value).strip().lower())
    if not match:
        raise ValueError("expiry must use a positive integer followed by m, h, or d, for example 30m, 8h, or 7d")
    amount = int(match.group("value"))
    unit = match.group("unit")
    return {"m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]


@dataclass(frozen=True)
class PolicyGrant:
    grant_id: str
    action: str
    kind: str
    reason: str
    created_at: str
    expires_at: str

    def as_dict(self, *, now: datetime) -> dict[str, Any]:
        payload = {
            "id": self.grant_id,
            "action": self.action,
            "kind": self.kind,
            "reason": self.reason,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }
        payload["expired"] = self.expiry <= now
        return payload

    @property
    def expiry(self) -> datetime:
        return _parse_timestamp(self.expires_at)


class PolicyGrantStore:
    schema_version = "1.0"

    def __init__(self, profile: Profile, *, clock: Callable[[], datetime] = utc_now):
        self.profile = profile
        self.clock = clock
        self.path = profile.workspace / ".aiplane" / "policy" / f"{profile.name}.json"

    def list(self, *, include_expired: bool = True) -> list[dict[str, Any]]:
        now = self.clock()
        records = [grant.as_dict(now=now) for grant in self._load()]
        return records if include_expired else [record for record in records if not record["expired"]]

    def active(self, action: str) -> list[PolicyGrant]:
        now = self.clock()
        return [grant for grant in self._load() if grant.action == action and grant.expiry > now]

    def grant(self, action: str, *, kind: str, reason: str, duration: str) -> dict[str, Any]:
        action = str(action).strip()
        reason = str(reason).strip()
        if not action:
            raise ValueError("policy action is required")
        if kind not in {"temporary_approval", "override"}:
            raise ValueError("policy grant kind must be temporary_approval or override")
        if not reason:
            raise ValueError("policy grant reason is required")
        now = self.clock()
        grant = PolicyGrant(
            grant_id=f"grant-{uuid4().hex[:12]}",
            action=action,
            kind=kind,
            reason=reason,
            created_at=now.isoformat(),
            expires_at=(now + parse_duration(duration)).isoformat(),
        )

        def update(payload: dict[str, Any]) -> dict[str, Any]:
            records = self._records_for_profile(payload)
            if any(item.action == action and item.expiry > now for item in records):
                raise ValueError(f"an active policy grant already exists for {action!r}")
            return {
                "schema_version": self.schema_version,
                "profile": self.profile.name,
                "grants": [
                    *[_stored_grant(item) for item in records],
                    _stored_grant(grant),
                ],
            }

        payload = atomic_update_json(self.path, update)
        stored = self._records_for_profile(payload)[-1]
        return stored.as_dict(now=now)

    def revoke(self, grant_id: str) -> dict[str, Any]:
        grant_id = str(grant_id).strip()
        removed: PolicyGrant | None = None
        now = self.clock()

        def update(payload: dict[str, Any]) -> dict[str, Any]:
            nonlocal removed
            records = self._records_for_profile(payload)
            kept: list[PolicyGrant] = []
            for record in records:
                if record.grant_id == grant_id:
                    removed = record
                else:
                    kept.append(record)
            if removed is None:
                raise ValueError(f"unknown policy grant {grant_id!r}")
            return {
                "schema_version": self.schema_version,
                "profile": self.profile.name,
                "grants": [_stored_grant(item) for item in kept],
            }

        atomic_update_json(self.path, update)
        if removed is None:
            raise RuntimeError("policy revoke invariant violated: grant was not removed")
        return removed.as_dict(now=now)

    def _load(self) -> list[PolicyGrant]:
        if not self.path.exists():
            return []
        import json

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("local policy grant state is unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("local policy grant state must be a JSON object")
        return self._records_for_profile(payload)

    def _records_for_profile(self, payload: dict[str, Any]) -> list[PolicyGrant]:
        profile_name = payload.get("profile")
        if profile_name not in {None, self.profile.name}:
            raise ValueError("local policy grant state belongs to a different profile")
        return _records(payload)


def _stored_grant(grant: PolicyGrant) -> dict[str, str]:
    return {
        "id": grant.grant_id,
        "action": grant.action,
        "kind": grant.kind,
        "reason": grant.reason,
        "created_at": grant.created_at,
        "expires_at": grant.expires_at,
    }


def _records(payload: dict[str, Any]) -> list[PolicyGrant]:
    if not payload:
        return []
    if payload.get("schema_version") not in {None, PolicyGrantStore.schema_version}:
        raise ValueError("unsupported local policy grant schema version")
    raw = payload.get("grants", [])
    if not isinstance(raw, list):
        raise ValueError("local policy grants must be a list")
    records: list[PolicyGrant] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("local policy grant entries must be objects")
        try:
            grant = PolicyGrant(
                grant_id=str(item["id"]),
                action=str(item["action"]),
                kind=str(item["kind"]),
                reason=str(item["reason"]),
                created_at=str(item["created_at"]),
                expires_at=str(item["expires_at"]),
            )
        except KeyError as exc:
            raise ValueError(f"local policy grant is missing {exc.args[0]}") from exc
        if grant.kind not in {"temporary_approval", "override"}:
            raise ValueError("local policy grant has an invalid kind")
        if not grant.grant_id or not grant.action or not grant.reason:
            raise ValueError("local policy grant contains an empty required field")
        _parse_timestamp(grant.created_at)
        _parse_timestamp(grant.expires_at)
        records.append(grant)
    return records


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("local policy grant contains an invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("local policy grant timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)
