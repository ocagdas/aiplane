"""Repository standard 1.0.0: shared version policy and atomic publication.

MIT licensed; see standards/repository/v1/LICENSE. Product adapters supply Git and mirrors.
"""

import contextlib
import io
import os
import re

PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def parse(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not PATTERN.fullmatch(value):
        raise ValueError("Version must be MAJOR.MINOR.PATCH without leading zeros")
    return tuple(map(int, value.split(".")))


def change_kind(previous: str, version: str) -> str:
    before, after = parse(previous), parse(version)
    if after <= before:
        raise ValueError("Version must increase")
    return next(name for name, old, new in zip(("major", "minor", "patch"), before, after) if old != new)


def bump(version: str, kind: str) -> str:
    parts = list(parse(version))
    index = ("major", "minor", "patch").index(kind)
    parts[index] += 1
    parts[index + 1 :] = [0] * (2 - index)
    return ".".join(map(str, parts))


def plan(previous: str | None, version: str, *, merged: bool, tagged: bool = False) -> dict:
    parse(version)
    if tagged:
        return {"mode": "none", "version": version, "reason": "already tagged"}
    if previous is not None and previous != version:
        kind = change_kind(previous, version)
        if merged:
            raise ValueError("PR merge changed the version")
        return {"mode": "tag", "version": version, "kind": kind}
    if merged:
        return {"mode": "patch", "version": bump(version, "patch"), "kind": "patch"}
    return {"mode": "none", "version": version, "reason": "no merged PR or version change"}


def publish(source, trunk, *, git, current, classify, write, tag, files, merged=False):
    git("check-ref-format", f"refs/heads/{trunk}")
    if git("status", "--porcelain"):
        raise ValueError("Publication requires a clean disposable checkout")
    if git("rev-parse", "HEAD") != source or os.getenv("GITHUB_SHA") != source:
        raise ValueError("Checkout and GITHUB_SHA must match the exact tested source commit")
    remote = f"refs/remotes/origin/{trunk}"
    git("fetch", "origin", f"refs/heads/{trunk}:{remote}", "--tags")
    identity = {"schema_version": 1, "source_commit": source}
    if git("rev-parse", remote) != source:
        return {**identity, "status": "superseded"}
    decision = classify(merged)
    if decision["mode"] == "none":
        return {**identity, "status": "unchanged"}
    with contextlib.redirect_stdout(io.StringIO()):
        if decision["mode"] == "patch":
            write(decision["version"])
            git("add", "--", *sorted(files))
            git("commit", "-m", f"chore(release): v{decision['version']}")
        selected = tag()
    # Never convert a rejected push into success. A new run rechecks the remote tip.
    git("push", "--atomic", "origin", f"HEAD:refs/heads/{trunk}", f"refs/tags/{selected}")
    return {
        **identity,
        "status": "published",
        "version": current(),
        "tag": selected,
        "version_commit": git("rev-parse", "HEAD"),
    }
