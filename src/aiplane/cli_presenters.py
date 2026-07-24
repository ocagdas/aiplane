from __future__ import annotations

import json
import sys
import threading

_AZ_SENSITIVE_FLAGS = {
    "--subscription",
    "--tenant",
    "--tenant-id",
    "--account-name",
    "--username",
    "--password",
    "--token",
    "--access-token",
    "--api-key",
    "--client-id",
    "--client-secret",
    "--sas-token",
    "--connection-string",
}

_AZ_SENSITIVE_JSON_KEYS = {
    "id",
    "tenantid",
    "subscriptionid",
    "userid",
    "username",
    "principalid",
    "clientid",
    "objectid",
    "accesstoken",
    "refreshtoken",
    "token",
    "password",
    "secret",
    "connectionstring",
}


def _redact_command_for_stderr(command: list[str]) -> str:
    parts: list[str] = []
    redact_next = False
    for item in command:
        token = str(item)
        lowered = token.lower()
        if redact_next:
            parts.append("[redacted]")
            redact_next = False
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            key_lower = key.lower()
            if key_lower in _AZ_SENSITIVE_FLAGS or _looks_sensitive_assignment(key):
                parts.append(f"{key}=[redacted]")
                continue
            parts.append(token if value else key)
            continue
        if lowered in _AZ_SENSITIVE_FLAGS:
            parts.append(token)
            redact_next = True
            continue
        parts.append(token)
    return " ".join(parts)


def _looks_sensitive_assignment(key: str) -> bool:
    key_lower = key.lower()
    return any(marker in key_lower for marker in ("token", "secret", "password", "apikey", "api_key", "key"))


def _redact_az_output_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return value
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return value
    redacted = _redact_json_payload(payload)
    return json.dumps(redacted, indent=2, ensure_ascii=False)


def _redact_json_payload(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in _AZ_SENSITIVE_JSON_KEYS:
                redacted[key] = "[redacted]"
                continue
            if key_lower == "user" and isinstance(item, dict):
                user_redacted = dict(item)
                if "name" in user_redacted and user_redacted["name"]:
                    user_redacted["name"] = "[redacted]"
                redacted[key] = _redact_json_payload(user_redacted)
                continue
            redacted[key] = _redact_json_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_json_payload(item) for item in value]
    return value


class _AzCommandReporter:
    def __init__(self, verbosity: int):
        self.verbosity = max(int(verbosity), 0)
        self._lock = threading.Lock()
        self._has_running_line = False
        self._dot_thread: threading.Thread | None = None
        self._dot_stop: threading.Event | None = None

    def report(self, event: dict[str, object]) -> None:
        phase = str(event.get("phase") or "")
        command = event.get("command")
        command_parts = [str(part) for part in command] if isinstance(command, list) else [str(command or "")]
        command_text = _redact_command_for_stderr(command_parts)
        if phase == "start":
            self._start_command_line(command_text)
            return
        if phase == "complete":
            self._stop_dot_line(clear_line=True)
            if self.verbosity >= 1:
                returncode = event.get("returncode", "?")
                self._write(f"[az] completed (exit {returncode}): {command_text}\n")
                stdout = event.get("stdout")
                stderr = event.get("stderr")
                if isinstance(stdout, str) and stdout.strip():
                    self._write(f"[az] stdout:\n{_redact_az_output_text(stdout).rstrip()}\n")
                if isinstance(stderr, str) and stderr.strip():
                    self._write(f"[az] stderr:\n{_redact_az_output_text(stderr).rstrip()}\n")

    def close(self) -> None:
        self._stop_dot_line(clear_line=True)

    def _start_command_line(self, command_text: str) -> None:
        self._stop_dot_line(clear_line=True)
        if self.verbosity <= 0 and self._has_running_line:
            self._write("\x1b[1A\r\x1b[2K")
        self._write(f"[az] running: {command_text}\n")
        self._has_running_line = True
        self._start_dot_line()

    def _start_dot_line(self) -> None:
        stop = threading.Event()
        self._dot_stop = stop
        thread = threading.Thread(target=self._dot_worker, args=(stop,), daemon=True)
        self._dot_thread = thread
        thread.start()

    def _dot_worker(self, stop: threading.Event) -> None:
        while not stop.wait(2):
            self._write(".")

    def _stop_dot_line(self, clear_line: bool) -> None:
        stop = self._dot_stop
        thread = self._dot_thread
        self._dot_stop = None
        self._dot_thread = None
        if stop:
            stop.set()
        if thread:
            thread.join(timeout=3)
        if clear_line:
            self._write("\r\x1b[2K\r")

    def _write(self, text: str) -> None:
        with self._lock:
            sys.stderr.write(text)
            sys.stderr.flush()


def _stderr_line_progress():
    longest = 0

    def progress(message: str) -> None:
        nonlocal longest
        if not message:
            if longest:
                sys.stderr.write("\r" + " " * longest + "\r")
                sys.stderr.flush()
                longest = 0
            return
        text = f"{message}..."
        longest = max(longest, len(text))
        sys.stderr.write("\r" + text.ljust(longest))
        sys.stderr.flush()

    return progress


def _hardware_show_text(payload: dict[str, object]) -> str:
    if not isinstance(payload, dict):
        return "hardware show\n(no data)"

    active = payload.get("active_selection", {})
    if not isinstance(active, dict):
        active = {}
    machine = payload.get("effective_machine", {})
    if not isinstance(machine, dict):
        machine = {}
    cpu = machine.get("cpu", {})
    memory = machine.get("memory", {})
    gpu = machine.get("gpu", {})
    stock = machine.get("stock", {})
    if not isinstance(cpu, dict):
        cpu = {}
    if not isinstance(memory, dict):
        memory = {}
    if not isinstance(gpu, dict):
        gpu = {}
    if not isinstance(stock, dict):
        stock = {}

    def _to_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)

    def _single_row_table(headers: dict[str, str], row: dict[str, str]) -> str:
        keys = list(headers)
        widths = {key: len(headers[key]) for key in keys}
        for key in keys:
            widths[key] = max(widths[key], len(row.get(key, "")))
        lines = [
            "".join(headers[key].ljust(widths[key] + 2) for key in keys),
            "".join(row[key].ljust(widths[key] + 2) for key in keys),
        ]
        return "\n".join(lines)

    active_row = {
        "name": _to_text(active.get("name")),
        "origin": _to_text(active.get("origin")),
        "custom": _to_text(active.get("custom")),
    }
    active_lines = _single_row_table(
        {"name": "NAME", "origin": "ORIGIN", "custom": "CUSTOM"},
        active_row,
    )

    effective_row = {
        "name": _to_text(machine.get("name")),
        "provider": _to_text(stock.get("provider")),
        "placement": _to_text(machine.get("placement")),
        "substrate": _to_text(machine.get("substrate")),
        "cpu_cores": _to_text(cpu.get("cores")),
        "cpu_threads": _to_text(cpu.get("threads")),
        "ram_gb": _to_text(memory.get("ram_gb")),
        "vram_gb": _to_text(gpu.get("vram_gb")),
        "total_vram_gb": _to_text(gpu.get("total_vram_gb")),
        "gpu_vendor": _to_text(gpu.get("vendor")),
        "gpu_model": _to_text(gpu.get("model")),
    }
    effective_lines = _single_row_table(
        {
            "name": "NAME",
            "provider": "PROVIDER",
            "placement": "PLACEMENT",
            "substrate": "SUBSTRATE",
            "cpu_cores": "CPU_CORES",
            "cpu_threads": "CPU_THREADS",
            "ram_gb": "RAM_GB",
            "vram_gb": "VRAM_GB",
            "total_vram_gb": "TOTAL_VRAM_GB",
            "gpu_vendor": "GPU_VENDOR",
            "gpu_model": "GPU_MODEL",
        },
        effective_row,
    )

    return "\n".join(
        [
            "hardware show",
            "active_selection",
            active_lines,
            "",
            "effective_machine",
            effective_lines,
        ]
    )


def _environment_doctor_text(payload: dict[str, object]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    rows: list[dict[str, str]] = []
    tool_rows: list[dict[str, str]] = []
    for section in [
        "installed",
        "missing_installable_by_aiplane",
        "missing_manual_or_platform_specific",
    ]:
        values = payload.get(section, [])
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            needed_for = item.get("needed_for", [])
            why = (
                ", ".join(str(value) for value in needed_for[:2])
                if isinstance(needed_for, list)
                else str(needed_for or "")
            )
            tool_rows.append(
                {
                    "name": str(item.get("name") or ""),
                    "kind": "tool",
                    "status": "installed" if item.get("installed") else "missing",
                    "required": str(item.get("requirement") or "optional"),
                    "why": why or str(item.get("description") or ""),
                }
            )
    rows.extend(
        sorted(
            tool_rows,
            key=lambda row: (
                0 if row["required"] == "mandatory" else 1,
                row["status"] != "installed",
                row["name"],
            ),
        )
    )
    values = payload.get("runtime_prerequisites", [])
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict):
            continue
        purpose = item.get("purpose", [])
        why = ", ".join(str(value) for value in purpose[:2]) if isinstance(purpose, list) else str(purpose or "")
        missing_required = item.get("missing_required", [])
        missing_count = len(missing_required) if isinstance(missing_required, list) else 0
        rows.append(
            {
                "name": str(item.get("runtime") or ""),
                "kind": "runtime",
                "status": (
                    "ready" if item.get("ok") else (f"missing {missing_count}" if missing_count else "needs setup")
                ),
                "required": "alternative" if payload.get("workflow") == "local_runtime" else "optional",
                "why": why,
            }
        )
    headers = {
        "name": "NAME",
        "kind": "TYPE",
        "status": "STATUS",
        "required": "REQUIRED",
        "why": "WHY",
    }
    keys = ["name", "kind", "status", "required", "why"]
    widths = {key: len(value) for key, value in headers.items()}
    for row in rows:
        for key in keys:
            limit = 52 if key == "why" else 24
            widths[key] = min(max(widths[key], len(row.get(key, ""))), limit)

    def clipped(value: str, width: int) -> str:
        return value if len(value) <= width else value[: max(0, width - 3)] + "..."

    lines = [
        f"environment doctor for profile {payload.get('profile', 'unknown')}",
        f"tools: {summary.get('tools_installed', 0)}/{summary.get('tools_checked', 0)} installed; runtime prerequisites missing: {summary.get('runtime_prerequisites_missing', 0)}",
        "",
        "  ".join(headers[key].ljust(widths[key]) for key in keys),
    ]
    for row in rows:
        lines.append("  ".join(clipped(row[key], widths[key]).ljust(widths[key]) for key in keys))
    workflow_readiness = (
        payload.get("workflow_readiness") if isinstance(payload.get("workflow_readiness"), dict) else None
    )
    if workflow_readiness is not None:
        lines.append("")
        workflow_name = workflow_readiness.get("name")
        workflow_state = workflow_readiness.get("readiness", "unknown")
        lines.append(f"workflow {workflow_name}: {workflow_state}")
        usable = workflow_readiness.get("usable_runtimes", [])
        if isinstance(usable, list) and usable:
            lines.append("usable runtimes: " + ", ".join(str(value) for value in usable))
        provider_status = workflow_readiness.get("vm_provider_status")
        if isinstance(provider_status, dict):
            provider_name = provider_status.get("name") or "unconfigured"
            provider_state = "usable" if provider_status.get("usable") else "unavailable"
            lines.append(f"Vagrant provider {provider_name}: {provider_state} ({provider_status.get('reason')})")
        actions = workflow_readiness.get("next_actions", [])
        if isinstance(actions, list) and actions:
            lines.append("workflow next actions:")
            lines.extend(f"- {action}" for action in actions)
    notes = payload.get("notes", [])
    if isinstance(notes, list) and notes:
        lines.append("")
        lines.append("next steps:")
        lines.extend(f"- {note}" for note in notes[:3])
    return "\n".join(lines)


def _public_discover_text(payload: dict[str, object]) -> str:
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    summary = provenance.get("summary") if isinstance(provenance.get("summary"), dict) else {}
    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
    lines = [
        f"aiplane discover for profile {payload.get('profile', 'unknown')}",
        f"hardware: CPU={hardware.get('cpu_count', 'unknown')}; RAM={hardware.get('memory_gb', 'unknown')}GB; GPUs={len(hardware.get('gpus', []) or [])}",
        f"runtimes: {len(payload.get('runtimes', []) or [])}; local_models: {len(payload.get('local_models', []) or [])}; endpoints: {len(payload.get('endpoints', []) or [])}; coding_tools: {len(payload.get('coding_tools', []) or [])}",
        "configuration sources (counted records): "
        f"detected={summary.get('detected_values', 0)}, "
        f"built_in={summary.get('generated_values', 0)}, "
        f"discovered_cache={summary.get('discovered_values', 0)}, "
        f"profile_configured={summary.get('user_supplied_values', 0)}, "
        f"unresolved={summary.get('unresolved_values', 0)}",
        "",
        f"next command: {payload.get('next_command')}",
    ]
    return "\n".join(lines)


def _public_recommend_text(payload: dict[str, object]) -> str:
    models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
    intent = str(payload.get("intent") or "balanced")
    recommended = models.get("recommended", []) if isinstance(models, dict) else []
    usable = models.get("usable", []) if isinstance(models, dict) else []
    remote = models.get("remote_or_cloud", []) if isinstance(models, dict) else []
    lines = [f"aiplane recommend ({intent})"]
    first = next((row for row in recommended if isinstance(row, dict)), None)
    if first is not None:
        lines.extend(
            [
                f"best local choice: {first.get('name')} (selection score: {float(first.get('selection_score', 0.0) or 0.0):.2f})",
                f"why: {first.get('reason')}",
                f"next command: aiplane integrations export continue --model {first.get('name')}",
            ]
        )
        guidance = first.get("runtime_guidance") if isinstance(first.get("runtime_guidance"), dict) else {}
        if guidance.get("next_command") and not guidance.get("ready"):
            lines.append(f"runtime preparation: {guidance['next_command']}")
    else:
        lines.append("best local choice: none")
    hidden = payload.get("hidden") if isinstance(payload.get("hidden"), dict) else {}
    nearest = hidden.get("nearest_miss") if isinstance(hidden.get("nearest_miss"), dict) else None
    if nearest:
        lines.append(f"nearest blocker: {nearest.get('name')}: {nearest.get('reason')}")
        lines.append(f"inspect/remedy: {nearest.get('remediation')}")
    lines.append(f"usable: {len(usable)}; remote_or_cloud: {len(remote)}")
    return "\n".join(lines)


def _quickstart_local_coding_text(payload: dict[str, object]) -> str:
    bootstrap = payload.get("bootstrap") if isinstance(payload.get("bootstrap"), dict) else {}
    doctor = payload.get("doctor") if isinstance(payload.get("doctor"), dict) else None
    lines = [
        f"local coding quickstart for profile {payload.get('profile', 'unknown')}",
        f"profile path: {bootstrap.get('path', '')}",
        f"created: {bootstrap.get('created', False)}; dry_run: {payload.get('dry_run', False)}",
    ]
    validation = bootstrap.get("validation") if isinstance(bootstrap.get("validation"), dict) else None
    if validation is not None:
        lines.append(f"profile validation: {'ok' if validation.get('ok') else 'issues found'}")
    pull = payload.get("pull") if isinstance(payload.get("pull"), dict) else None
    if pull is not None:
        lines.append(
            f"pull: {'executed' if pull.get('executed') else 'preview'}; "
            f"model: {pull.get('model')}; runtime: {pull.get('runtime', 'n/a')}"
        )
    if doctor is not None:
        summary = doctor.get("summary") if isinstance(doctor.get("summary"), dict) else {}
        lines.append(
            f"doctor: {'ok' if doctor.get('ok') else 'issues found'}; "
            f"needs_attention: {summary.get('blocking', 0)}; further_actions: {summary.get('warnings', 0)}"
        )
        # show top blocking checks and simple suggestions
        if doctor is not None:
            blocking: list[tuple[str, str]] = []
            warnings: list[tuple[str, str]] = []
            for section in doctor.get("sections", []) or []:
                if not isinstance(section, dict):
                    continue
                section_name = str(section.get("name") or "general")
                for check in section.get("checks", []) or []:
                    if not isinstance(check, dict):
                        continue
                    reason = check.get("reason") or check.get("detail") or ""
                    # simple suggestion mapping with exact CLI snippets
                    if check.get("name") == "model_catalog":
                        suggestion = (
                            "Try: `aiplane models refresh --dry-run`; "
                            "`aiplane models list --group-by runtime`; "
                            "`aiplane models promote DISCOVERED_ENTRY_NAME --as ALIAS`"
                        )
                    elif section.get("name") == "model_defaults" or str(check.get("name", "")).endswith("_model"):
                        role_arg = check.get("name") or "<role>"
                        suggestion = (
                            "Try: `aiplane models refresh --dry-run`; "
                            "`aiplane models promote DISCOVERED_ENTRY_NAME --as ALIAS`; "
                            f"`aiplane models use {role_arg} ALIAS`"
                        )
                    elif section.get("name") == "environment":
                        suggestion = (
                            "Try: `aiplane environment doctor --required-only` then install missing CLIs listed above."
                        )
                    elif section.get("name") == "endpoints" or str(check.get("name", "")).startswith("endpoint:"):
                        suggestion = "Try: `aiplane runtimes status <runtime>` or `aiplane providers test <provider>`. If provider is disabled, run `aiplane providers enable <provider>`."
                    elif section.get("name") == "integrations":
                        suggestion = "Try: `aiplane integrations list`; `aiplane integrations roles <tool>`; `aiplane integrations plan <tool>`."
                    else:
                        suggestion = "See `aiplane doctor --profile <name>` for details."
                    check_name = str(check.get("name") or "check")
                    if section_name == "integrations" and check_name.startswith("integration:"):
                        check_name = check_name.split(":", 1)[1]
                    item = f"{check_name}: {reason} -> {suggestion}"
                    if not check.get("ok"):
                        blocking.append((section_name, item))
                    elif check.get("warning"):
                        warnings.append((section_name, item))

            if blocking:
                lines.append("")
                lines.append(f"recommended actions ({len(blocking)}):")
                current_root = ""
                for root, item in blocking:
                    if root != current_root:
                        lines.append(f"- {root}:")
                        current_root = root
                    lines.append(f"  - {item}")
            if warnings:
                lines.append("")
                lines.append(f"further actions/status ({len(warnings)}):")
                current_root = ""
                for root, item in warnings:
                    if root != current_root:
                        lines.append(f"- {root}:")
                        current_root = root
                    lines.append(f"  - {item}")
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    if readiness:
        lines.append("")
        lines.append(f"readiness: {readiness.get('status', 'unknown')}")
        reason = readiness.get("reason")
        if reason:
            lines.append(f"reason: {reason}")
        choices = readiness.get("setup_choices", [])
        if isinstance(choices, list) and choices:
            lines.append("setup choices (choose one):")
            for choice in choices:
                if isinstance(choice, dict):
                    lines.append(f"- {choice.get('name')}: {choice.get('command')}")
                    lines.append(f"  then: {choice.get('then')}")
    lines.append("")
    lines.append("next action:")
    commands = payload.get("commands", [])
    if isinstance(commands, list):
        lines.extend(f"- {command}" for command in commands)
    return "\n".join(lines).rstrip()
