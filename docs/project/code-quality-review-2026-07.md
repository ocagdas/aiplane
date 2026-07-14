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
4. **SEC-4 — Strict SSH target and endpoint validation.** **Status: completed.** A shared validation boundary now accepts only DNS/IPv4/IPv6 hosts, restricted SSH usernames, integer ports 1-65535, and credential-free `http`/`https` endpoint URLs. Option-like destinations, combined `user@host` host fields, whitespace/control characters, malformed authorities, URL fragments, and unsupported schemes fail before argv construction. IPv6 forwarding is bracketed correctly. Remote profile commands use `shlex.join` for values interpreted by the remote shell. Focused evidence: 49 remote/validation tests passed; quick gate 14 passed; full suite 396 passed; representative CLI plan and malicious-input rejection passed.

5. **COMPAT-1 — Explicit platform capability boundary.** **Status: completed.** `HostPlatform` centralizes OS, Linux distribution family, architecture, and WSL detection. Runtime install/update helpers fail with `unsupported_platform` unless running on native Ubuntu/Debian; WSL and other systems use vendor installers. Hardware discovery skips Linux procfs/PCI/ROCm/GPU commands on non-Linux hosts and reports probe coverage. Tool platform reporting uses the same detector, and the published matrix separates portable inspection from host mutation. Synthetic Ubuntu, Debian, Fedora, WSL, macOS, and Windows tests ensure unsupported operations do not execute host commands. Focused compatibility/hardware suite: 78 passed; combined COMPAT-1/ARCH-2 suite: 117 passed; final full suite: 422 passed.
6. **SEC-2 — Fail-closed MCP mutation guards.** **Status: completed.** MCP stdio is read-only by default. Every actual mutation requires both operator startup with `--allow-writes` and `confirm=true` on that individual tool call; either missing guard is audited as `blocked` before manager dispatch. Schemas expose the confirmation contract, confirmation metadata is not forwarded to domain managers, and refresh dry-runs remain read-only. Broader cloud, shell, secret, install, pull, and benchmark writes remain unavailable. Focused MCP/security contracts: 37 passed; combined SEC-2/REL-3 suite 63 passed; quick gate 14 passed; full suite 409 passed.
7. **SEC-3 — Audit secret redaction and data minimization.** **Status: completed.** Redaction covers sensitive mapping keys, adjacent and assigned CLI flags, bearer/provider/AWS token forms, and whole PEM-bearing values. Tool audit records retain only action metadata, safe file targets, argument counts, and exception types; command output, raw arguments, and exception messages are excluded. MCP failures return sanitized type-only messages, while audit appends are serialized and durable. Focused evidence: persistence/secret suite 10 passed; expanded relevant suite 96 passed; quick gate 14 passed; full suite 367 passed.
8. **REL-3 — Sanitized CLI process boundary.** **Status: completed.** Expected operational errors pass through secret redaction; unexpected exceptions expose only their type and an opt-in `--debug` hint. `--debug` or `AIPLANE_DEBUG=true` deliberately enables tracebacks with an explicit sensitive-context warning. Broken pipes exit quietly without a secondary flush failure, and keyboard interruption returns status 130. Focused CLI boundary/governance smoke coverage: 26 passed; combined SEC-2/REL-3 suite 63 passed; real pipefail check passed; quick gate 14 passed; full suite 409 passed.
9. **ARCH-2 — Domain persistence and cloud-adapter decomposition.** **Status: completed.** Model reconciliation remains in `model_refresh.py`, while `ModelCatalogStore` now exclusively owns curated/generated paths, serialization, generated-cache invalidation, banners, and atomic writes; catalog and refresh modules cannot bypass it. Machine Azure HTTP pricing/normalization moved to injectable `AzureRetailPricing`, and Azure subprocess timeout/progress/redacted account parsing moved to `azure_cli.py`. Structural tests cap `model_catalog.py` below 1,850 lines and `machines.py` below 1,000 and forbid persistence/external-I/O drift back into domain modules. Focused architecture/domain suite: 64 passed; combined COMPAT-1/ARCH-2 suite: 117 passed; final full suite: 422 passed.
10. **DOC-1 — Public onboarding documentation contracts.** **Status: completed.** Bare `aiplane export` examples now name the concrete `continue` target, the empty README workflow heading is removed, and both user-documentation indexes retain sequential Start here and Common workflows numbering. Contract tests reject ambiguous export examples, adjacent empty headings, and numbering drift. Focused evidence: 13 contract tests passed; quick gate: 17 passed; full suite: 425 passed.

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
