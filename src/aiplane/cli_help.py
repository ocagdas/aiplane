from __future__ import annotations

import argparse


COMMAND_TIERS = (
    ("Core workflow", ("discover", "doctor", "recommend", "export", "quickstart")),
    (
        "Advanced and supporting",
        (
            "config",
            "profiles",
            "hardware",
            "machines",
            "models",
            "integrations",
            "runtimes",
            "providers",
            "environment",
            "tools",
            "credentials",
            "mcp",
            "audit",
            "policy",
            "remote",
        ),
    ),
    (
        "Experimental",
        (
            "run",
            "tool",
            "code",
            "agents",
            "chat",
            "bridge",
            "launch",
            "session",
            "orchestrators",
            "stacks",
            "deploy",
            "benchmarks",
        ),
    ),
)


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    def _format_action(self, action):
        if isinstance(action, argparse._SubParsersAction) and action.dest == "command":
            help_by_command = {choice.dest: choice.help for choice in action._choices_actions}
            categorized = {command for _, commands in COMMAND_TIERS for command in commands}
            if categorized != set(help_by_command):
                missing = sorted(set(help_by_command) - categorized)
                unknown = sorted(categorized - set(help_by_command))
                raise RuntimeError(f"top-level command tiers are out of sync: missing={missing}, unknown={unknown}")
            lines = ["  command\n"]
            for tier, commands in COMMAND_TIERS:
                lines.append(f"\n    {tier}:\n")
                for command in commands:
                    lines.append(f"      {command:<18}{help_by_command[command]}\n")
            return "".join(lines)
        return super()._format_action(action)
