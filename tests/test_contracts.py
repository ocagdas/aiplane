from __future__ import annotations

from pathlib import Path
import argparse
import re
import tomllib
import warnings

from aiplane.cli_parser import build_parser
from aiplane.integration_contracts import ALL_INTEGRATION_TOOLS, required_roles
from aiplane.mcp import TOOL_SCHEMAS, mcp_manifest
from aiplane.model_resources import (
    accelerator_api_requirements,
    gpu_vendor_requirement,
    matches_accelerator_api_requirement,
    matches_gpu_vendor_requirement,
    parameter_billions,
    resource_guess,
)
from aiplane.runtime_catalog import (
    PROVIDER_ENDPOINT_DEFAULTS,
    RUNTIME_DEFINITIONS,
    SOURCE_DEFINITIONS,
)
from aiplane.runtime_pull import runtime_pull_support


PROJECT_PLAN = Path("docs/project/project-plan.md")


PLAN_OWNERS = {
    "Command Coverage": "STATUS.md",
    "Roadmap": "ROADMAP.md",
    "Integration Roadmap": "docs/project/integration-design.md",
    "Product Adoption Backlog": "TODO.md",
    "P0 Maintainer Checklist": "TODO.md",
    "Developer-Preview Scope Freeze": "docs/project/preview-scope.md",
    "Public Launch Review": "docs/project/launch-criteria.md",
    "Public Demo Plan": "docs/user/demo.md",
    "External Trial Evidence": "docs/project/trial-evidence/recording-guide.md",
}


def _project_plan_section(title: str) -> str:
    text = Path(PLAN_OWNERS[title]).read_text(encoding="utf-8")
    marker = f"## {title}\n"
    if text.startswith(f"# {title}\n"):
        return text.split("\n", 1)[1]
    assert marker in text, title
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def test_project_planning_documents_have_single_owners() -> None:
    text = PROJECT_PLAN.read_text(encoding="utf-8")
    for name in ("PURPOSE.md", "STATUS.md", "VALIDATION.md", "ROADMAP.md", "TODO.md"):
        assert Path(name).is_file()
        assert name in text
    assert len(text.splitlines()) < 30
    for title in PLAN_OWNERS:
        assert _project_plan_section(title).strip()


def test_integration_contracts_define_tools_and_roles_once() -> None:
    assert "continue" in ALL_INTEGRATION_TOOLS
    assert "generic-mcp" in ALL_INTEGRATION_TOOLS
    assert {"codex", "copilot-cli", "copilot-vscode"} <= set(ALL_INTEGRATION_TOOLS)
    assert [role["name"] for role in required_roles("continue")] == [
        "chat",
        "autocomplete",
        "embedding",
    ]
    assert required_roles("generic-mcp") == []


def test_model_resource_helpers_parse_and_match_requirements() -> None:
    assert parameter_billions("vendor/model-7b-q4") == 7.0
    assert parameter_billions("qwen2.5-14B-instruct") == 14.0
    assert resource_guess(9, ["chat"]) == (16, 32, 6, 10)

    model = {"gpu_vendor_requirement": "any", "accelerator_api_requirements": ["cuda"]}
    assert gpu_vendor_requirement(model) == "generic"
    assert accelerator_api_requirements(model) == ["cuda"]
    assert matches_gpu_vendor_requirement(model, "nvidia")
    assert matches_gpu_vendor_requirement(model, "generic")
    assert matches_accelerator_api_requirement(model, "cuda")
    assert not matches_accelerator_api_requirement(model, "generic")


def test_mcp_manifest_tools_have_input_schemas() -> None:
    names = {tool["name"] for tool in mcp_manifest()["tools"]}
    assert names <= set(TOOL_SCHEMAS)


def test_runtime_definition_reexports_keep_catalog_contracts_stable() -> None:
    assert RUNTIME_DEFINITIONS["ollama"]["model_sources"] == ["ollama", "gguf_import"]
    assert SOURCE_DEFINITIONS["huggingface_gguf"]["typical_runtimes"] == [
        "llamacpp",
        "localai",
        "ollama",
    ]
    assert PROVIDER_ENDPOINT_DEFAULTS["ollama"]["endpoint"] == "http://localhost:11434"


def test_runtime_pull_support_is_pure_and_source_based() -> None:
    assert runtime_pull_support("ollama", {"provider": "llamacpp", "source": "huggingface_gguf"})["supported"]
    unsupported = runtime_pull_support("localai", {"provider": "llamacpp", "source": "huggingface_gguf"})
    assert not unsupported["supported"]
    assert "manual" in unsupported["reason"]


def test_aiplane_skill_is_versioned_and_not_template_text() -> None:
    skill = Path("skills/aiplane/SKILL.md")
    text = skill.read_text(encoding="utf-8")
    assert "name: aiplane" in text
    assert re.search(r"Skill version: \d+\.\d+\.\d+", text)
    assert "TODO" not in text
    assert "environment doctor and configuration compiler" in text
    assert "control-plane" not in text
    assert "tests/test_mvp.py" not in text
    assert "tests/test_quick_smoke.py" in text
    manifest = Path("skills/aiplane/agents/openai.yaml").read_text(encoding="utf-8")
    assert "environment-configuration" in manifest
    assert "control-plane" not in manifest


def test_cli_command_families_are_owned_outside_composition_root() -> None:
    root = Path("src/aiplane/cli.py").read_text(encoding="utf-8")
    for module in (
        "cli_public.py",
        "cli_execution.py",
        "cli_providers.py",
        "cli_runtimes.py",
        "cli_launch_support.py",
        "cli_profile_support.py",
        "cli_presenters.py",
        "cli_public_workflows.py",
    ):
        assert (Path("src/aiplane") / module).is_file()
    for command in ("discover", "quickstart", "run", "code", "providers", "runtimes"):
        assert f'if args.command == "{command}"' not in root
    line_count = len(root.splitlines())
    if line_count >= 500:
        warnings.warn(
            f"src/aiplane/cli.py has {line_count} lines; keep extracting command-family ownership before it reaches 600",
            stacklevel=1,
        )
    assert line_count < 600
    for helper in (
        "_launch_plan",
        "_validate_profile",
        "_AzCommandReporter",
        "_hardware_show_text",
        "_public_discover",
        "_bootstrap_local_profile",
        "_quickstart_local_coding",
    ):
        assert f"def {helper}" not in root
        assert f"class {helper}" not in root


def test_dev_dependencies_include_no_isolation_build_backend() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = project["project"]["optional-dependencies"]["dev"]
    assert "setuptools==83.0.0" in dev_dependencies


def test_full_check_uses_configurable_file_level_parallelism() -> None:
    script = Path("scripts/check.sh").read_text(encoding="utf-8")
    assert "AIPLANE_TEST_WORKERS:-4" in script
    assert "--dist loadfile" in script


def test_make_check_is_strict_and_contributor_commands_are_maintained() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "format-check:\n\tpython -m ruff format --check src tests scripts" in makefile
    assert "check: format-check lint standard-check test-clean" in makefile
    assert "$(PYTHON) scripts/check_repository_standard.py" in makefile
    assert "test_mvp.py" not in contributing
    assert "tests/test_contracts.py" in contributing
    assert "tests/test_quick_smoke.py" in contributing
    assert "environment doctor and configuration compiler" in contributing


def test_documentation_split_points_to_canonical_development_and_architecture_docs() -> None:
    development = Path("docs/development/setup.md").read_text(encoding="utf-8")

    assert "`docs/development/setup.md`: dependency, test, and contributor workflows." in development
    assert "`docs/architecture.md`: product strategy and architecture boundary." in development


def test_external_io_calls_are_centralized_in_boundaries() -> None:
    violations = []
    for path in Path("src/aiplane").glob("*.py"):
        if path.name == "boundaries.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in ("subprocess.run(", "subprocess.Popen(", "urlopen("):
            if token in text:
                violations.append(f"{path}:{token}")
    assert violations == []


PUBLIC_ONBOARDING_DOCS = (
    Path("README.md"),
    Path("docs/user/index.md"),
    Path("docs/user/README.md"),
    Path("docs/user/overview.md"),
)


def test_public_onboarding_uses_concrete_export_commands_and_nonempty_sections() -> None:
    for path in PUBLIC_ONBOARDING_DOCS:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?m)^\s*aiplane export\s*$", text), path
        assert "aiplane export continue" in text, path
        assert not re.search(r"(?m)^#{1,6} .+\n(?=#{1,6} )", text), path


def test_user_workflow_indexes_have_sequential_numbering() -> None:
    for path in (Path("docs/user/index.md"), Path("docs/user/README.md")):
        text = path.read_text(encoding="utf-8")
        expected_sections = (("Start here", [1, 2, 3, 4, 5]), ("Common workflows", [1, 2, 3, 4, 5]))
        for heading, expected in expected_sections:
            section = text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
            actual = [int(value) for value in re.findall(r"(?m)^(\d+)\. ", section)]
            assert actual == expected, (path, heading, actual)


def test_manual_and_evidence_runbooks_use_real_top_level_commands() -> None:
    parser = build_parser()
    subcommands = next(action.choices for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    for path in (Path("docs/user/manual-test-checklist.md"), Path("docs/user/evidence-collection.md")):
        text = path.read_text(encoding="utf-8")
        assert text.count("```") % 2 == 0, path
        commands = re.findall(r"(?:aiplane|python -m aiplane) ([a-z][a-z-]*)", text)
        assert commands, path
        assert all(command in subcommands for command in commands), (path, commands)
    for path in (Path("docs/user/manual-test-checklist.md"), Path("docs/user/evidence-collection.md")):
        assert (
            "AIPLANE_RUN_PERFORMANCE=1 python -m pytest -q tests/performance/test_catalog_query_performance.py"
            in path.read_text(encoding="utf-8")
        )


def test_provider_and_codex_validation_instructions_match_safe_contracts() -> None:
    manual = Path("docs/user/manual-test-checklist.md").read_text(encoding="utf-8")
    evidence = Path("docs/user/evidence-collection.md").read_text(encoding="utf-8")

    assert "aiplane providers test ollama" in manual
    assert "ollama_tags" in manual
    assert 'aiplane launch --tool codex --model "$CHAT_ALIAS" --dry-run' in manual
    assert "Codex built-in local Ollama or LM Studio providers" in manual
    assert "loopback endpoint" in manual
    assert "run_capture 12-provider-ollama aiplane providers test ollama" in evidence
    assert "run_capture 24-codex-launch aiplane launch --tool codex --model local_chat --dry-run" in evidence


def test_public_onboarding_links_and_code_fences_are_valid() -> None:
    for path in PUBLIC_ONBOARDING_DOCS:
        text = path.read_text(encoding="utf-8")
        assert text.count("```") % 2 == 0, path
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            local_target = target.split("#", 1)[0]
            if not local_target or "://" in local_target or local_target.startswith("mailto:"):
                continue
            assert (path.parent / local_target).exists(), (path, target)


def test_public_positioning_agrees_across_metadata_and_launch_docs() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    description = project["project"]["description"].lower()
    assert "environment doctor" in description
    assert "configuration compiler" in description

    launch_review = _project_plan_section("Public Launch Review")
    for name, document in (
        ("README.md", Path("README.md").read_text(encoding="utf-8")),
        ("PURPOSE.md", Path("PURPOSE.md").read_text(encoding="utf-8")),
        ("project plan: public launch review", launch_review),
    ):
        opening = document[:2000].lower()
        assert "environment doctor" in opening, name
        assert "configuration compiler" in opening, name

    readme_opening = Path("README.md").read_text(encoding="utf-8")[:2000]
    assert "aiplane quickstart local-coding --dry-run" in readme_opening
    assert "First outcome:" in readme_opening
    assert "Know what fits. See what is missing. Generate the right config." in readme_opening

    readme = Path("README.md").read_text(encoding="utf-8")
    for outcome_heading in (
        "## The problem it solves",
        "## What you get",
        "## Install",
        "## Core onboarding flow",
        "## Quick local Ollama demo",
    ):
        assert readme.count(outcome_heading) == 1
    assert readme.index("First outcome:") < readme.index("## Install")
    assert readme.index("## The problem it solves") < readme.index("## What you get")
    assert readme.index("## What you get") < readme.index("## Install")
    assert "<summary><strong>Expand the full install" in readme
    assert readme.index("## Core onboarding flow") < readme.index("## Advanced and experimental commands")
    readme_lower = readme.lower()
    for stale_breadth in (
        "control plane",
        "control-plane",
        "agentic environments",
        "provisioning and automation",
        "benchmark and evaluation",
        "machines and stacks",
        "mcp",
    ):
        assert stale_breadth not in readme_lower

    keywords = set(project["project"]["keywords"])
    assert {"environment", "configuration", "diagnostics", "reproducibility"} <= keywords
    assert keywords.isdisjoint({"mcp", "agents", "benchmarks", "stacks", "provisioning"})


def test_install_channels_and_release_workflows_are_explicit() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    validator = Path("scripts/verify_install_channels.py").read_text(encoding="utf-8")
    setup = Path("docs/user/setup.md").read_text(encoding="utf-8")

    for os_runner in ("ubuntu-latest", "macos-14", "windows-latest"):
        assert os_runner in ci
    for channel in ("pip", "pipx", "uv"):
        assert f"def verify_{channel}" in validator
    assert "python scripts/verify_install_channels.py dist" in ci
    assert "verify_platform_contracts" in validator
    assert "Validate real pip, pipx, and uv installed-wheel lifecycles" in ci
    assert "tests/test_platform_support.py" not in ci
    for portable_command in ("profiles", "hardware", "recommend", "policy", "integrations"):
        assert f'"{portable_command}"' in validator
    assert "unsupported_platform" in validator
    assert "tags:" in release and '- "v*"' in release
    assert 'scripts/version.py classify-release --tag "$TAG"' in release
    assert "gh release create" in release
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    package_init = Path("src/aiplane/__init__.py").read_text(encoding="utf-8")
    assert f'__version__ = "{project["project"]["version"]}"' in package_init
    assert {"Homepage", "Documentation", "Repository", "Issues"} <= set(project["project"]["urls"])
    assert "pypa/gh-action-pypi-publish" not in release
    for command in (
        "uv tool install",
        "pipx install",
        "python -m pip install",
        "uv tool uninstall",
        "pipx uninstall",
        "python -m pip uninstall",
    ):
        assert command in setup
    assert "Do not assume index publication" in setup


def test_public_workflow_and_terminology_do_not_regress_to_stale_promises() -> None:
    for path in (Path("docs/user/index.md"), Path("docs/user/README.md"), Path("docs/user/overview.md")):
        text = path.read_text(encoding="utf-8")
        assert "one exact next action" in text, path
        assert "prints the next" not in text, path

    assert "control-plane" not in _project_plan_section("Integration Roadmap").lower()
    for path in (Path("SECURITY.md"), Path("docs/user/machines-and-stacks.md")):
        assert "control-plane" not in path.read_text(encoding="utf-8").lower(), path


def test_p0_documentation_sweep_stays_open_until_user_demonstrations() -> None:
    backlog = _project_plan_section("Product Adoption Backlog")

    assert "**P0 completion gate.**" in backlog
    assert "after all numbered P0 work is complete" in backlog
    assert "must be repeated after the user-testing demonstrations" in backlog
    assert "interim pass does not close this gate" in backlog


def test_open_backlog_retains_unique_ordered_task_identifiers() -> None:
    backlog = _project_plan_section("Product Adoption Backlog")
    numbered = [int(value) for value in re.findall(r"(?m)^(\d+)\. ", backlog)]
    assert numbered == sorted(set(numbered))


def test_public_demo_plan_is_bounded_reproducible_and_uses_current_commands() -> None:
    text = _project_plan_section("Public Demo Plan")

    assert text.count("### Primary public adoption cut") == 1
    assert text.count("## P0 validation recording") == 2
    assert "one introductory product video" in text
    for command in (
        "aiplane quickstart local-coding --dry-run",
        "aiplane discover",
        "aiplane doctor",
        "aiplane recommend",
        "aiplane export continue",
        "aiplane profiles render local-dev",
        "aiplane profiles validate local-dev",
        "aiplane profiles repair local-dev --file models.yaml --dry-run",
        "aiplane hardware export-machine --name gpu-workstation",
        "aiplane machines import gpu-workstation.machine.yaml",
        "aiplane remote tunnel plan --target gpu_workstation_ssh",
    ):
        assert command in text

    assert "cmp demo-backup/local-dev.profile.json demo-backup/local-dev.restored.profile.json" in text
    assert "cannot reconstruct user customizations" in text
    assert "It does not start a process" in text
    assert "control plane" not in text.lower()
    assert "mvp_0." not in text


def test_readme_and_demo_plan_keep_end_to_end_local_evaluator_order() -> None:
    commands = [
        "uv tool install ./aiplane-0.1.0-py3-none-any.whl",
        "aiplane profiles bootstrap-local --no-overwrite --no-discovery --no-hardware-discovery",
        "aiplane hardware discover",
        "aiplane models refresh --provider ollama --query chat --limit 25",
        "aiplane models list --provider ollama --runtime ollama --role chat --current-machine",
        "aiplane models promote DISCOVERED_ALIAS --as local_chat",
        "aiplane integrations setup codex --model local_chat --runtime ollama",
        "aiplane runtimes status ollama",
        "aiplane export codex --model local_chat",
        "aiplane export copilot-cli --model local_chat --format json --offline",
        "aiplane export copilot-vscode --model local_chat",
        "aiplane chat --model local_chat",
    ]
    documents = (
        ("README.md", Path("README.md").read_text(encoding="utf-8")),
        ("project plan: public demo", _project_plan_section("Public Demo Plan")),
    )
    for name, document in documents:
        positions = [document.index(command) for command in commands]
        assert positions == sorted(positions), name
        assert "--identity alias" in document
        assert "--identity model" in document
        assert "--identity both" in document


def test_install_verifier_is_portable_and_never_starts_supported_tunnels() -> None:
    verifier = Path("scripts/verify_install_channels.py").read_text(encoding="utf-8")

    assert "model_path.name" in verifier
    assert 'openai_config.get("model") != "portable-smoke.gguf"' in verifier
    assert 'cli("remote", "tunnel", "plan"' in verifier
    assert 'if system == "Windows":' in verifier
    assert 'if platform.system() in {"Darwin", "Windows"}:' not in verifier
    darwin_guard, windows_guard = verifier.split('if system == "Windows":', 1)
    assert '"tunnel",\n                "start"' not in darwin_guard
    assert '"tunnel",\n                "start"' in windows_guard


def test_backlog_is_portable_and_gates_remain_open() -> None:
    backlog = _project_plan_section("Product Adoption Backlog")

    assert "/home/" not in backlog
    assert "**P0 completion gate.**" in backlog
    assert "independent users reproduce each" in backlog
    assert "must be repeated after the user-testing demonstrations" in backlog


def test_primary_adoption_cut_contains_only_the_core_command_story() -> None:
    text = _project_plan_section("Public Demo Plan")
    primary = text.split("### Primary public adoption cut", 1)[1].split("### P0 workflow-validation recordings", 1)[0]

    commands = re.findall(r"(?m)^aiplane .+$", primary)
    assert commands == [
        "aiplane quickstart local-coding --dry-run",
        "aiplane discover",
        "aiplane doctor",
        "aiplane recommend",
        "aiplane export codex --model local_chat",
        "aiplane export copilot-cli --model local_chat --format json --offline",
        "aiplane export copilot-vscode --model local_chat",
    ]
    for advanced in (" chat ", " run ", " code ", " mcp ", " stacks ", " orchestrators ", " deploy ", " benchmarks "):
        assert advanced not in primary.lower()


def test_ci_and_release_policy_have_explicit_owners() -> None:
    policy = Path("VERSIONING.md").read_text()
    for term in (
        "--merged",
        "--github-output",
        "--verify-only",
        "superseded",
        "atomic",
        "merge base",
        "Minor/major",
        "Patch",
    ):
        assert term in policy
    assert "Quality gate" in Path("CI.md").read_text()
    assert "rollback" in Path("docs/user/release-verification.md").read_text().lower()


def test_release_workflow_is_checksummed_versioned_and_quality_gated() -> None:
    workflow = Path(".github/workflows/release.yml").read_text()
    assert "uses: ./.github/workflows/ci.yml" in workflow
    assert "needs.qualification.result == 'success' && needs.qualification.outputs.go == 'true'" in workflow
    assert "ref: ${{ needs.classify.outputs.commit }}" in workflow
    assert 'scripts/build_release.py --tag "$TAG" --output dist' in workflow
    assert "python scripts/verify_release_manifest.py dist" in workflow
    assert "subject-checksums: dist/SHA256SUMS" in workflow
    assert "for artifact in dist/*.whl dist/*.tar.gz dist/provenance.json; do" in workflow
    assert "python scripts/render_release_notes.py" in workflow
    assert "--notes-file RELEASE_NOTES.md" in workflow
    assert "cmp dist/SHA256SUMS downloaded/SHA256SUMS" in workflow
    assert "scripts/build_release.py --verify-only --output downloaded" in workflow


def test_ci_exposes_one_stable_quality_gate_and_documents_hosted_protection() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text()
    protection = Path("docs/project/repository-protection.md").read_text()
    assert "name: Quality gate" in workflow
    assert "needs: [checks, compatibility, install-channels]" in workflow
    assert "name: quality-gate" in workflow
    assert "steps.gate.outputs.go" in workflow
    assert "merge_group:" in workflow
    assert "workflow_dispatch:" in workflow
    for term in (
        "Release gate",
        "Quality gate",
        "Require a pull request before merging",
        "Block force pushes",
        "targeting `v*`",
    ):
        assert term in protection


def test_preview_scope_freeze_keeps_advanced_surface_out_of_public_promise() -> None:
    freeze = _project_plan_section("Developer-Preview Scope Freeze")
    coverage = _project_plan_section("Command Coverage")

    assert "Until the P0 gates close" in freeze
    assert "No new integration, runner, orchestrator, stack, benchmark, deployment, MCP-write capability" in freeze
    assert "## Exception process" in freeze
    assert "synchronized changes to strategy, roadmap, command coverage, help, and public documentation" in freeze
    assert "| Experimental |" in coverage


def test_every_demo_timeline_step_has_exact_commands_and_spoken_narration() -> None:
    text = _project_plan_section("Public Demo Plan")
    matches = list(re.finditer(r"(?m)^#{4,5} (\d):(\d{2})-(\d):(\d{2}) — .+$", text))

    assert len(matches) == 16
    for index, match in enumerate(matches):
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else text.find("## Optional fourth video", match.end())
        )
        section = text[match.end() : end]
        assert "On screen:" in section, match.group(0)
        assert "Exact command" in section, match.group(0)
        assert "Narration:" in section, match.group(0)
        narration = " ".join(line[2:] for line in section.splitlines() if line.startswith("> "))
        words = len(re.findall(r"\b[\w’-]+\b", narration))
        start_minute, start_second, end_minute, end_second = map(int, match.groups())
        seconds = (end_minute * 60 + end_second) - (start_minute * 60 + start_second)
        assert words / seconds * 60 <= 140, match.group(0)


def test_successful_trunk_merge_versions_tags_and_uploads_a_bound_wheel() -> None:
    ci = Path(".github/workflows/ci.yml").read_text()
    workflow = Path(".github/workflows/version.yml").read_text()
    assert "needs.quality-gate.result == 'success' && needs.quality-gate.outputs.go == 'true'" in ci
    assert "github.event_name == 'push'" in ci
    assert "github.sha == inputs.source" in workflow
    assert "inputs.go == 'true'" in workflow
    assert "scripts/merged_pr.py --source" in workflow
    assert "github.workflow == 'CI'" in ci
    assert "github.workflow == 'CI'" in workflow
    assert "scripts/publish_version.py --source" in workflow
    assert "ref: ${{ inputs.source }}" in workflow
    assert "git checkout -B" not in workflow
    assert "for attempt" not in workflow
    assert "AIPLANE_VERSIONING_APP_ID" in workflow
    assert "AIPLANE_VERSIONING_APP_PRIVATE_KEY" in workflow
    assert "needs.publish.outputs.status == 'published'" in workflow
    assert 'scripts/build_release.py --tag "$TAG" --output artifacts' in workflow
    assert "scripts/verify_install_channels.py artifacts --channel pip" in workflow
    assert "retention-days: 30" in workflow


def test_release_policy_auto_publishes_milestones_and_keeps_manual_patch_override() -> None:
    workflow = Path(".github/workflows/release.yml").read_text()
    assert 'tags:\n      - "v*"' in workflow
    assert 'classify-release --tag "$TAG" --github-output' in workflow
    assert "needs.classify.outputs.publish == 'true' || github.event_name == 'workflow_dispatch'" in workflow
    assert 'gh workflow run verify-release.yml --ref "$TRUNK" -f tag="$TAG"' in workflow


def test_published_release_workflow_verifies_every_os_and_install_owner() -> None:
    workflow = Path(".github/workflows/verify-release.yml").read_text(encoding="utf-8")

    for os_runner in ("ubuntu-latest", "macos-14", "windows-latest"):
        assert os_runner in workflow
    assert "channel: [pip, pipx, uv]" in workflow
    assert "gh release download" in workflow
    assert "python scripts/verify_release_manifest.py release" in workflow
    assert "attestations: read" in workflow
    assert "for artifact in release/*.whl release/*.tar.gz release/provenance.json; do" in workflow
    assert 'gh attestation verify "$artifact"' in workflow
    assert 'python scripts/verify_install_channels.py release --channel "$CHANNEL"' in workflow
    assert "python scripts/write_release_evidence.py" in workflow
    assert "python scripts/validate_trial_evidence.py" in workflow
    assert "uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "retention-days: 90" in workflow


def test_profile_render_export_and_replay_terminology_is_consistent() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    overview = Path("docs/user/overview.md").read_text(encoding="utf-8")
    schema = Path("docs/user/profile-schema.md").read_text(encoding="utf-8")
    demo = _project_plan_section("Public Demo Plan")
    roadmap = _project_plan_section("Roadmap")

    for document in (readme, overview, schema, demo):
        assert "editable" in document.lower()
        assert "profiles render" in document
        assert "export" in document.lower()
        assert "replay" in document.lower()

    for document in (readme, overview, schema):
        assert "profiles archive" in document
        assert "profiles restore" in document
        assert "profiles compare" in document
        assert "profiles drift" in document
        assert "never overwritten" in document.lower()

    assert "cannot currently restore the YAML" in readme
    assert "prints to stdout" in readme
    assert "capability-equivalent" in readme
    assert "not currently accepted as restore input" in schema
    assert "Priority 13: Replay approved profiles across machines" in roadmap
    for classification in (
        "exact equality",
        "capability-equivalent variance",
        "material incompatibility",
        "unresolved evidence",
    ):
        assert classification in roadmap
    assert "Do not copy credentials, model weights" in Path("STATUS.md").read_text()


def test_materialized_catalog_commands_and_hardware_limits_are_documented() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    providers = Path("docs/user/providers.md").read_text(encoding="utf-8")
    hardware = Path("docs/user/hardware.md").read_text(encoding="utf-8")
    development = Path("docs/development/setup.md").read_text(encoding="utf-8")
    plan = Path("STATUS.md").read_text(encoding="utf-8")

    assert "models catalog-cache status" in readme
    for command in ("catalog-cache status", "catalog-cache rebuild", "catalog-cache clear"):
        assert command in providers
    assert "--catalog-cache off" in providers
    assert "--property quantization=q4" in providers
    assert "largest" in hardware and "single visible GPU" in hardware
    assert "topology is captured" in hardware.lower()
    assert "never treated as one interchangeable pool" in hardware
    assert "benchmark_catalog_queries.py --sizes 1000 10000 100000" in development
    assert "materialized model catalog and indexed queries" in plan


def test_multi_client_replay_and_recommendation_provenance_are_documented() -> None:
    overview = Path("docs/user/overview.md").read_text(encoding="utf-8")
    schema = Path("docs/user/profile-schema.md").read_text(encoding="utf-8")
    workflows = Path("docs/user/workflows.md").read_text(encoding="utf-8")
    machines = Path("docs/user/machines-and-stacks.md").read_text(encoding="utf-8")
    hardware = Path("docs/user/hardware.md").read_text(encoding="utf-8")
    plan = Path("STATUS.md").read_text(encoding="utf-8")

    for document in (overview, schema, workflows, machines, plan):
        assert "profiles replay-check" in document
    for document in (overview, schema, workflows, machines):
        assert "--client-archive" in document
    assert "at least two" in schema
    assert "deterministic and read-only" in machines
    assert "versioned provenance" in hardware
    assert "benchmark sample count" in hardware
    assert "Ordinary\nsmoke-test" in hardware
    assert "recommendation-critical schema hardening" in plan
