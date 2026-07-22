from __future__ import annotations

import pytest

from aiplane.cli_profile_support import _profile_summary
from aiplane.cli_public_workflows import _public_discover
from aiplane.evidence import EVIDENCE_STATES, evidence_provenance, evidence_source
from aiplane.hardware import HardwareManager
from aiplane.integrations import IntegrationManager
from aiplane.local_doctor import local_coding_doctor
from tests.profile_fixtures import _isolated_test_profile


REQUIRED_FIELDS = {"schema_version", "evidence_state", "sample_count", "sources", "uncertainty", "summary"}


def assert_evidence_contract(payload: dict[str, object]) -> None:
    assert REQUIRED_FIELDS <= payload.keys()
    assert payload["schema_version"] == "1.0"
    assert payload["evidence_state"] in {"complete", "partial", "unresolved"}
    assert isinstance(payload["sample_count"], int)
    assert payload["sample_count"] >= 0
    assert isinstance(payload["uncertainty"], list)
    assert isinstance(payload["sources"], list)
    for source in payload["sources"]:
        assert {"name", "state", "source"} <= source.keys()
        assert source["state"] in EVIDENCE_STATES


def test_evidence_builder_classifies_complete_partial_and_unresolved_inputs() -> None:
    configured = evidence_source("profile", "configured", "models.yaml")
    assert evidence_provenance([configured])["evidence_state"] == "complete"
    partial = evidence_provenance([configured], uncertainty=["measurement unavailable", "measurement unavailable"])
    assert partial["evidence_state"] == "partial"
    assert partial["uncertainty"] == ["measurement unavailable"]
    unresolved = evidence_provenance([evidence_source("benchmark", "unresolved", None)])
    assert unresolved["evidence_state"] == "unresolved"
    with pytest.raises(ValueError, match="unknown evidence state"):
        evidence_source("bad", "assumed", "test")


def test_public_planning_surfaces_share_the_evidence_contract() -> None:
    with _isolated_test_profile() as profile:
        discovery = _public_discover(profile)
        doctor = local_coding_doctor(profile)
        profile_show = _profile_summary(profile)
        plan = IntegrationManager(profile).plan("continue")
        recommendation = HardwareManager(profile).recommend(include_not_recommended=True)

    for payload in (
        discovery["provenance"],
        doctor["provenance"],
        profile_show["provenance"],
        plan["provenance"],
        recommendation["provenance"],
    ):
        assert_evidence_contract(payload)
    rows = [row for group in recommendation["models"].values() for row in group]
    assert rows
    for row in rows:
        assert_evidence_contract(row["provenance"])
    assert (
        discovery["provenance"]["summary"]["user_supplied_values"]
        == discovery["provenance"]["summary"]["configured_values"]
    )
    assert "not measured task-quality evidence" in " ".join(plan["provenance"]["uncertainty"])
