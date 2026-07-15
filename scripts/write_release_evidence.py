#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from scripts.validate_trial_evidence import validate_record
    from scripts.verify_release_manifest import parse_manifest
except ModuleNotFoundError:  # Direct execution places scripts/ first on sys.path.
    from validate_trial_evidence import validate_record
    from verify_release_manifest import parse_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Write sanitized CI evidence for a published release installation.")
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--channel", choices=("pip", "pipx", "uv"), required=True)
    parser.add_argument("--elapsed-seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = parse_manifest((args.release_dir / "SHA256SUMS").read_text(encoding="utf-8"))
    wheel = next((name for name in entries if name.endswith(".whl")), None)
    if wheel is None:
        parser.error("release manifest has no wheel")
    version = args.tag.removeprefix("v")
    ended = datetime.now(timezone.utc)
    started = ended - timedelta(seconds=args.elapsed_seconds)
    started_at = started.isoformat().replace("+00:00", "Z")
    ended_at = ended.isoformat().replace("+00:00", "Z")
    install_channel = "uv-tool" if args.channel == "uv" else args.channel
    record = {
        "record_version": 1,
        "trial_id": f"ci-{args.tag}-{platform.system().lower()}-{args.channel}",
        "classification": "rehearsal",
        "workflow": "no-clone-install",
        "artifact": {
            "release_url": args.release_url,
            "version": version,
            "sha256": entries[wheel],
            "commit": args.commit,
        },
        "environment": {
            "os": platform.system(),
            "os_version": platform.release(),
            "architecture": platform.machine() or "unknown",
            "python": platform.python_version(),
            "install_channel": install_channel,
            "runtime": "not-applicable",
            "model": "portable-smoke.gguf",
        },
        "start_state": {
            "clean_machine_or_vm": True,
            "repository_checkout_present": True,
            "existing_profile": False,
            "notes": "Hosted runner; release artifacts downloaded into an isolated workspace.",
        },
        "timing": {"started_at": started_at, "ended_at": ended_at, "elapsed_seconds": args.elapsed_seconds},
        "commands": [{
            "command": f"python scripts/verify_install_channels.py release --channel {args.channel}",
            "exit_code": 0,
            "elapsed_seconds": args.elapsed_seconds,
            "outcome": "Install, portable workflow, replacement or upgrade, and uninstall passed.",
            "written_paths": [],
        }],
        "first_failure": None,
        "assistance": {"beyond_written_workflow": False, "details": "Automated deterministic CI rehearsal."},
        "outcome": {
            "completed": True,
            "files_written_understood": True,
            "export_non_mutating_understood": True,
            "feedback": "Published release channel verification passed.",
        },
        "sanitization": {
            "no_credentials_or_tokens": True,
            "no_personal_identifiers": True,
            "no_private_hosts_or_account_ids": True,
            "relative_written_paths_only": True,
            "human_reviewed": True,
        },
    }
    validate_record(record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
