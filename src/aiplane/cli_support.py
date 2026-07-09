from __future__ import annotations

import sys


def refresh_progress():
    if not sys.stderr.isatty():
        return None

    def report(event: str, provider: str, detail: str) -> None:
        if event == "done":
            print("\r" + " " * 100 + "\r", file=sys.stderr, end="", flush=True)
            return
        label = {
            "connecting": "connecting",
            "succeeded": "succeeded",
            "failed": "failed",
        }.get(event, event)
        message = f"refresh: {label} {provider}"
        if detail:
            message += f" - {detail}"
        print("\r" + message[:100].ljust(100), file=sys.stderr, end="", flush=True)

    return report


def parse_provider_limits(values: list[str]) -> dict[str, int]:
    limits: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("provider limit must use PROVIDER=COUNT, for example huggingface=25")
        provider, raw_count = value.split("=", 1)
        provider = provider.strip()
        if not provider:
            raise ValueError("provider limit is missing provider name")
        try:
            count = int(raw_count.strip())
        except ValueError as exc:
            raise ValueError(f"provider limit for {provider} must be an integer") from exc
        if count < 1:
            raise ValueError(f"provider limit for {provider} must be at least 1")
        limits[provider] = count
    return limits


def parse_settings(settings: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for setting in settings:
        if "=" not in setting:
            raise ValueError(f"invalid setting {setting!r}; expected key=value")
        key, value = setting.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"invalid setting {setting!r}; key is empty")
        parsed[key] = parse_setting_value(value.strip())
    return parsed


def parse_setting_value(value: str) -> object:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
