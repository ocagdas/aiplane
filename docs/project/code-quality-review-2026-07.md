# Code Quality and Safety Review — July 2026

This is the persistent issue register for the repository-wide structure, safety,
security, crash-resilience, consistency, documentation, and bug review completed
on 2026-07-14. Update completion evidence here instead of repeating the analysis.

1. **SEC-1 — CLI tool approval bypass.** Risky `aiplane tool` operations were
   constructed with unconditional approval. **Status: completed.** Require interactive approval or an explicit per-invocation `--yes`,
   fail closed without a TTY, and test denied, approved, and read-only paths. Focused evidence: `python -m pytest -q tests/test_tool_approvals.py tests/test_environment_tools_benchmarks.py` (20 passed).
2. **SEC-2 — MCP writes execute without a real guard.** The guarded-write
   manifest overstates policy enforcement; refresh, defaults, hardware/runtime
   selection, and tunnel lifecycle can mutate immediately. **Status: open.**
3. **SAFE-1 — Tunnel PID reuse can terminate an unrelated process.** Tunnel state
   lacks process identity and normalized target names can collide. **Status: open.**
4. **SEC-3 — Audit secret redaction is incomplete.** Adjacent CLI flag values,
   common token formats, command output, and exception strings can leak.
   **Status: open.**
5. **REL-1 — Configuration writes are not atomic or concurrency-safe.** Direct
   read/modify/write paths can truncate files or lose concurrent updates.
   **Status: open.**
6. **SEC-4 — SSH target validation permits option-like values.** Host/user and
   endpoint validation should use strict syntax and allowed schemes. **Status: open.**
7. **REL-2 — Corrupt JSONL records can crash `audit tail`.** Malformed or partial
   records need bounded recovery and warnings. **Status: open.**
8. **DOC-1 — Onboarding documents contain invalid bare `aiplane export`
   examples and duplicate workflow numbering.** **Status: open.**
9. **ARCH-1 — CLI composition-root decomposition.** **Status: completed.** `cli.py` is now a 456-line parser/dispatch composition root. Launch/session planning, profile views/validation, presenters/progress reporting, and public onboarding workflows have focused module owners. Structural contracts enforce a sub-500-line root and prevent extracted helpers from drifting back. Evidence: focused suite 89 passed; quick gate 14 passed; full suite 349 passed.
10. **ARCH-2 — Large domain modules mix persistence, discovery, reconciliation,
    validation, and rendering.** Start with model catalog persistence and machine
    cloud inventory/pricing boundaries. **Status: open.**
11. **REL-3 — Unexpected CLI errors and broken pipes lack a sanitized boundary.**
    Add clean pipe handling and opt-in debug tracebacks. **Status: open.**

Preserve argv-based subprocess execution, injectable external-I/O boundaries,
resolved workspace path containment, synthetic profiles, and tests that block
unintended external network access. Follow the order above unless a newly found
release blocker requires reprioritization. Every completed item needs focused tests
and aligned user/project documentation.
