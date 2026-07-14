from __future__ import annotations

from pathlib import Path
import re


REQUIRED_AREAS = (
    "Credential references",
    "Redaction and errors",
    "Generated configuration",
    "Shell and installer helpers",
    "MCP adapter",
    "Tunnel ownership",
    "Profile trust",
    "Audit sensitivity",
)


def test_threat_model_maps_every_required_area_to_evidence_and_a_limitation() -> None:
    text = Path("docs/project/threat-model.md").read_text(encoding="utf-8")
    rows = {
        cells[0]: cells
        for line in text.splitlines()
        if line.startswith("|") and len(cells := [cell.strip() for cell in line.strip("|").split("|")]) == 4
    }

    for area in REQUIRED_AREAS:
        assert area in rows, f"missing threat-model area: {area}"
        _, control, evidence, limitation = rows[area]
        assert control
        test_paths = re.findall(r"`(tests/[^`]+\.py)(?:::[^`]*)?`", evidence)
        assert test_paths, f"missing test evidence for: {area}"
        assert all(Path(path).is_file() for path in test_paths)
        assert limitation, f"missing explicit limitation for: {area}"


def test_security_policy_links_threat_model_and_uses_current_product_boundary() -> None:
    text = Path("SECURITY.md").read_text(encoding="utf-8")

    assert "docs/project/threat-model.md" in text
    assert "environment doctor and configuration compiler" in text
    assert "control-plane CLI" not in text
