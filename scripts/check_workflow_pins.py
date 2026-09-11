"""Require consistent immutable action pins and exact version comments."""

import argparse
from pathlib import Path
import re

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


def mapping(node):
    if not isinstance(node, MappingNode):
        raise ValueError("Expected a workflow mapping")
    result = {}
    for key, value in node.value:
        if not isinstance(key, ScalarNode) or key.value in result or key.value == "<<":
            raise ValueError("Duplicate, merged or non-scalar workflow key")
        result[key.value] = value
    return result


def action_nodes(document):
    workflow = mapping(document)
    jobs = mapping(workflow.get("jobs"))
    for job in jobs.values():
        fields = mapping(job)
        if "uses" in fields:
            yield fields["uses"]
        if "steps" in fields:
            steps = fields["steps"]
            if not isinstance(steps, SequenceNode):
                raise ValueError("Expected a workflow steps sequence")
            for step in steps.value:
                fields = mapping(step)
                if "uses" in fields:
                    yield fields["uses"]


def validate(root):
    pins = {}
    paths = (
        sorted(path for path in (Path(root) / ".github/workflows").iterdir() if path.suffix in (".yml", ".yaml"))
        if (Path(root) / ".github/workflows").is_dir()
        else []
    )
    if not paths:
        raise ValueError("No workflows found")
    for path in paths:
        source = path.read_text(encoding="utf-8")
        try:
            document = yaml.compose(source, Loader=yaml.BaseLoader)
        except yaml.YAMLError as error:
            raise ValueError(f"Invalid workflow YAML: {path.name}") from error
        lines = source.splitlines()
        for node in action_nodes(document):
            if not isinstance(node, ScalarNode):
                raise ValueError(f"Action reference must be a string: {path.name}")
            reference = node.value
            if reference.startswith("./"):
                continue
            action, separator, commit = reference.partition("@")
            if not separator or not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ValueError(f"Action needs a full commit pin: {path.name}: {action}")
            # Comments are not YAML nodes. Read only the suffix after the parsed scalar,
            # allowing closing flow delimiters, never '#' inside a quoted value.
            mark = node.end_mark
            suffix = lines[mark.line][mark.column :] if mark.line < len(lines) else ""
            version = re.fullmatch(r"[\s}\]]*# (v[0-9]+\.[0-9]+\.[0-9]+)\s*", suffix)
            if not version:
                raise ValueError(f"Action needs an exact version comment after its value: {path.name}: {action}")
            pin = (commit, version[1])
            if action in pins and pins[action] != pin:
                raise ValueError(f"Inconsistent action pin: {action} in {path.name}")
            pins[action] = pin
    return pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        pins = validate(args.repo)
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    print(f"Workflow pins passed ({len(pins)} actions)")


if __name__ == "__main__":
    main()
