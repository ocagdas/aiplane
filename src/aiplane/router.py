from __future__ import annotations

from .audit import AuditLogger
from .backends import BackendResult
from .hardware import HardwareManager
from .model_catalog import ModelCatalog
from .models import AuditEvent, Profile
from .policy import PolicyEngine
from .secrets import contains_secret


class Router:
    def __init__(self, profile: Profile, audit: AuditLogger):
        self.profile = profile
        self.policy = PolicyEngine(profile)
        self.audit = audit
        self.catalog = ModelCatalog(profile)

    def route(
        self,
        task: str,
        prefer_escalation: bool = False,
        model_name: str | None = None,
        dry_run: bool = False,
        ignore_hardware_fit: bool = False,
    ) -> BackendResult:
        if prefer_escalation and contains_secret(task):
            self._record_block("backend:managed_service", "secret detected")
            raise PermissionError("secret detected; managed-service escalation blocked")

        selected = self._select_model(prefer_escalation, model_name)
        provider = str(selected["model"].get("provider", ""))
        local = bool(selected["model"].get("local", False))
        action = f"model:{selected['name']}"

        self._check_model_policy(selected["name"])

        if local and not ignore_hardware_fit:
            fit = HardwareManager(self.profile).check_model_fit(selected["model"])
            if not fit.usable:
                self._record_block(
                    action, "model does not satisfy active hardware requirements", provider=provider, hardware_fit=False
                )
                raise RuntimeError(
                    f"model does not satisfy active hardware requirements: {fit.reason}; "
                    "rerun with --ignore-hardware-fit to override"
                )
        if not local:
            self._check_cloud_allowed(task)

        if dry_run:
            result = BackendResult(
                "dry_run",
                self._dry_run_text(task, selected["name"], selected["model"]),
                escalated=not local,
            )
            self._record_allowed(
                action,
                provider=provider,
                dry_run=True,
                escalated=result.escalated,
            )
            return result

        try:
            result = self.catalog.complete(selected["name"], task)
        except Exception as exc:
            self._record_block(action, str(exc), provider=provider)
            raise
        result = BackendResult(result.backend, result.text, escalated=not local)
        self._record_allowed(
            action,
            provider=provider,
            backend=result.backend,
            escalated=result.escalated,
        )
        return result

    def _select_model(self, prefer_escalation: bool, model_name: str | None) -> dict[str, object]:
        models = self.catalog.models()
        if model_name:
            if model_name not in models:
                raise ValueError(f"unknown model: {model_name}")
            model = models[model_name]
            if not bool(model.get("enabled", True)):
                raise ValueError(f"model is disabled: {model_name}")
            return {"name": model_name, "model": model}

        enabled = [(name, model) for name, model in models.items() if bool(model.get("enabled", True))]
        if prefer_escalation:
            default = self.catalog.default_model("managed_service_model")
            if default and not bool(default["model"].get("local", False)):
                return {"name": default["name"], "model": default["model"]}
            for name, model in enabled:
                if not bool(model.get("local", False)):
                    return {"name": name, "model": model}
        default = self.catalog.default_model("self_managed_model")
        if default and bool(default["model"].get("local", False)):
            return {"name": default["name"], "model": default["model"]}
        for name, model in enabled:
            if bool(model.get("local", False)):
                return {"name": name, "model": model}
        if enabled:
            return {"name": enabled[0][0], "model": enabled[0][1]}
        raise ValueError("profile has no enabled models")

    def _check_model_policy(self, model_name: str) -> None:
        decision = self.policy.model_decision(model_name)
        if decision.allowed:
            return
        self._record_block(
            f"model:{model_name}",
            decision.reason,
        )
        raise PermissionError(decision.reason)

    def _check_cloud_allowed(self, task: str) -> None:
        if contains_secret(task):
            self._record_block("backend:managed_service", "secret detected")
            raise PermissionError("secret detected; managed-service escalation blocked")
        cloud_decision = self.policy.cloud_decision()
        if not cloud_decision.allowed:
            self._record_block(
                "backend:managed_service",
                cloud_decision.reason,
            )
            raise PermissionError(cloud_decision.reason)

    def _record_allowed(self, action: str, **details: object) -> None:
        self.audit.record(
            AuditEvent(
                "route",
                self.profile.name,
                action,
                "allowed",
                details,
            )
        )

    def _record_block(self, action: str, reason: str, **details: object) -> None:
        self.audit.record(
            AuditEvent(
                "route",
                self.profile.name,
                action,
                "blocked",
                {
                    "reason": reason,
                    **details,
                },
            )
        )

    def _dry_run_text(self, task: str, model_name: str, model: dict[str, object]) -> str:
        return (
            f"Would run task with model alias: {model_name}\n"
            f"Provider: {model.get('provider')}\n"
            f"Provider model: {model.get('model')}\n"
            f"Escalated/managed-service: {not bool(model.get('local', False))}\n\n"
            f"Prompt:\n{task}"
        )
