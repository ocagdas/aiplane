"""Shared artifact provenance contract; MIT, standards/repository/v1/LICENSE."""

import hashlib
import json
import os
import re

if __package__:
    from . import repository_release as shared
else:
    import repository_release as shared


def write_provenance(directory, *, version, commit, tag=None, dirty=False, distribution="wheel-source"):
    artifacts = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.iterdir())
        if p.name.endswith((".whl", ".tar.gz"))
    }
    value = {
        "schema_version": 1,
        "distribution": distribution,
        "build_kind": "release" if tag else "candidate",
        "version": version,
        "tag": tag,
        "source_commit": commit,
        "version_commit": commit if tag else None,
        "dirty": dirty,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "artifacts": artifacts,
    }
    (directory / "provenance.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value


def verify_provenance(value, artifacts, distribution="wheel-source"):
    shared.parse(value["version"])
    commit = value["source_commit"]
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
        or value.get("distribution") != distribution
        or type(value.get("dirty")) is not bool
        or not isinstance(commit, str)
        or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit)
        or value.get("artifacts") != artifacts
        or not (value.get("run_id") is None or isinstance(value["run_id"], str))
    ):
        raise ValueError("Invalid provenance identity or artifact digests")
    if value["build_kind"] == "release":
        if value["tag"] != "v" + value["version"] or value["version_commit"] != commit or value["dirty"]:
            raise ValueError("Release provenance must bind a clean matching tag/commit")
    elif value["build_kind"] == "candidate":
        if value["tag"] is not None or value["version_commit"] is not None:
            raise ValueError("Candidate provenance cannot claim a release tag")
    else:
        raise ValueError("Unknown provenance build kind")
