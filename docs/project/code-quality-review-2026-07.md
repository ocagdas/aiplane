# Code Quality and Safety Review — July 2026

This is the persistent issue register for the repository-wide structure, safety,
security, crash-resilience, consistency, documentation, and bug review completed
on 2026-07-14. Update completion evidence here instead of repeating the analysis.

## Prioritized Items

1. **REL-2 — Recover safely from corrupt audit JSONL records.** **Status:
   completed.** `AuditLogger.tail_report()` returns recent valid events plus
   metadata-only warnings, skips malformed/non-object records, identifies a likely
   truncated final write, validates limits, and keeps `tail()` compatible. The CLI
   preserves machine-readable stdout and reports skipped line numbers/types on
   stderr without echoing corrupt content. Focused evidence: 24 tests passed; quick gate 14 passed; full suite 353 passed.
2. **SAFE-1 — Identity-safe SSH tunnel lifecycle.** **Status: completed.** Tunnel ownership is stored as versioned atomic JSON with PID plus a captured process-start/command identity. Status and stop verify identity; reused or stale PIDs are never signalled. Linux uses a PID file descriptor when available to close the verify/signal race, other POSIX systems use a captured `ps` fingerprint, and unsupported identity capture terminates the newly spawned process without saving state. Target state/log names include a stable hash to prevent normalized-name collisions. Focused evidence: remote/boundary suite 23 passed; expanded integration suite 70 passed; production Linux identity check passed; quick gate 14 passed; full suite 357 passed.
3. **REL-1 — Atomic, concurrency-safe persistence.** **Status: completed.** All production text writes now use the shared persistence boundary: same-directory fsynced temporary files and atomic replacement for snapshots, plus locked fsynced append for audit JSONL. Per-file IPC locks use nonblocking OS advisory locking with one bounded deadline and jittered polling; nested persistence locks are rejected to prevent lock-order cycles, and process exit releases OS ownership. Transactional YAML updates prevent lost concurrent mutations. Tests cover permissions, cleanup, thread and separate-process contention, timeout/recovery, nested-lock rejection, and direct-write drift. Focused evidence: persistence/secret suite 10 passed; expanded relevant suite 96 passed; quick gate 14 passed; full suite 367 passed.
4. **SEC-4 — SSH target validation permits option-like values.** Host/user and
   endpoint validation should use strict syntax and allowed schemes. **Status: open.**

5. **COMPAT-1 — Gate host-specific operations by operating system and Linux
   distribution.** **Status: open.** Inventory commands and probes that depend on
   Linux, Ubuntu/Debian, `apt`, `systemd`, procfs, Bash, GPU utilities, package
   layouts, or other host-specific behavior. Centralize platform/distribution
   capability detection; never execute or recommend an incompatible operation on
   macOS, Windows, a non-Linux host, or a non-Ubuntu Linux distribution. CLI help,
   doctors, plans, dry-runs, and errors must state supported platforms and
   distinguish `unsupported_platform` from a missing tool or failed command.
   Document supported/unsupported paths, including an explicit WSL policy, and
   cover them with synthetic platform/distribution tests that do not depend on the
   developer machine.
6. **SEC-2 — MCP writes execute without a real guard.** The guarded-write manifest
   overstates policy enforcement; refresh, defaults, hardware/runtime selection,
   and tunnel lifecycle can mutate immediately. **Status: open.**
7. **SEC-3 — Audit secret redaction and data minimization.** **Status: completed.** Redaction covers sensitive mapping keys, adjacent and assigned CLI flags, bearer/provider/AWS token forms, and whole PEM-bearing values. Tool audit records retain only action metadata, safe file targets, argument counts, and exception types; command output, raw arguments, and exception messages are excluded. MCP failures return sanitized type-only messages, while audit appends are serialized and durable. Focused evidence: persistence/secret suite 10 passed; expanded relevant suite 96 passed; quick gate 14 passed; full suite 367 passed.
8. **REL-3 — Unexpected CLI errors and broken pipes lack a sanitized boundary.**
   Add clean pipe handling and opt-in debug tracebacks. **Status: open.**
9. **ARCH-2 — Large domain modules mix persistence, discovery, reconciliation,
   validation, and rendering.** Start with model catalog persistence and machine
   cloud inventory/pricing boundaries. **Status: open.**
10. **DOC-1 — Onboarding documents contain invalid bare `aiplane export` examples
   and duplicate workflow numbering.** **Status: open.**

## Completed Earlier

- **SEC-1 — CLI tool approval bypass.** Risky `aiplane tool` operations now require
  interactive approval or explicit per-invocation `--yes` and fail closed without
  a TTY. Focused evidence: 20 tests passed.
- **ARCH-1 — CLI composition-root decomposition.** `cli.py` is a 456-line
  parser/dispatch composition root. Launch/session planning, profile
  views/validation, presenters/progress reporting, and public onboarding workflows
  have focused owners. Structural contracts enforce a sub-500-line root and
  prevent extracted helpers from drifting back. Evidence: focused suite 89 passed;
  quick gate 14 passed; full suite 349 passed.

Preserve argv-based subprocess execution, injectable external-I/O boundaries,
resolved workspace path containment, synthetic profiles, and tests that block
unintended external network access. Follow the order above unless a newly found
release blocker requires reprioritization. Every completed item needs focused tests
and aligned user/project documentation.
