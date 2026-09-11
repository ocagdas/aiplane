"""The shared pin policy must fail closed on inconsistent action references."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workflow_pin_policy", ROOT / "scripts/check_workflow_pins.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class WorkflowPinsTests(unittest.TestCase):
    def test_drift_and_missing_pins_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / ".github/workflows"
            directory.mkdir(parents=True)
            (directory / "ci.yml").write_text(
                "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@" + "a" * 40 + " # v7.0.1\n",
                encoding="utf-8",
            )
            other = directory / "verify-release.yml"
            for reference in ("b" * 40 + " # v7.0.1", "a" * 40 + " # v7.0.0", "v7", "a" * 40 + " # v7"):
                with self.subTest(reference=reference):
                    other.write_text(
                        "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@" + reference + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        POLICY.validate(root)
            other.write_text(
                "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@" + "a" * 40 + " # v7.0.1\n",
                encoding="utf-8",
            )
            self.assertEqual(len(POLICY.validate(root)), 1)

    def test_no_workflows_is_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                POLICY.validate(Path(temporary))

    def check_steps(self, steps):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / ".github/workflows"
            directory.mkdir(parents=True)
            (directory / "ci.yaml").write_text(
                "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n" + steps,
                encoding="utf-8",
            )
            return POLICY.validate(root)

    def test_alternate_yaml_syntax_cannot_hide_unpinned_actions(self):
        for steps in (
            "      - {uses: actions/checkout@main}\n",
            '      - "uses": "actions/checkout@main"\n',
            "      - uses: >-\n          actions/checkout@main\n",
            "      - &shared {uses: actions/checkout@main}\n      - *shared\n",
        ):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                self.check_steps(steps)

    def test_quoted_flow_and_aliased_pins_are_checked(self):
        reference = "actions/checkout@" + "a" * 40
        for steps in (
            '      - "uses": "' + reference + '" # v7.0.1\n',
            "      - {uses: " + reference + "} # v7.0.1\n",
            "      - &shared {uses: " + reference + "} # v7.0.1\n      - *shared\n",
        ):
            with self.subTest(steps=steps):
                self.assertEqual(self.check_steps(steps), {"actions/checkout": ("a" * 40, "v7.0.1")})

    def test_run_text_is_not_an_action_and_local_actions_need_no_pin(self):
        self.assertEqual(
            self.check_steps("      - run: |\n          uses: example@main\n      - uses: ./local-action\n"), {}
        )

    def test_invalid_shapes_and_duplicate_keys_fail_closed(self):
        for steps in (
            "      - {uses: [bad]}\n",
            "      - {uses: ./local, uses: actions/checkout@main}\n",
            "      - {<<: {uses: actions/checkout@main}}\n",
            "      - {uses: [\n",
        ):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                self.check_steps(steps)

    def test_reusable_workflow_references_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / ".github/workflows"
            directory.mkdir(parents=True)
            workflow = directory / "ci.yml"
            workflow.write_text("jobs: {test: {uses: org/repo/.github/workflows/ci.yml@main}}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                POLICY.validate(root)
            workflow.write_text(
                "jobs: {test: {uses: org/repo/.github/workflows/ci.yml@" + "a" * 40 + "}} # v1.2.3\n",
                encoding="utf-8",
            )
            self.assertEqual(len(POLICY.validate(root)), 1)
