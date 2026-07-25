# Reviewed patch workflow

Use this advanced workflow to inspect and explicitly apply a Git patch that you have already obtained and reviewed. It is a narrow working-tree helper, not a code-generation or agent feature: `aiplane` never creates a diff, calls a model, stages files, or commits changes.

Keep the patch file inside the selected workspace. Inspection is read-only; application changes the working tree only after all safeguards pass.

## Inspect a patch

```bash
aiplane patches inspect changes.patch
```

The JSON result contains a content hash, changed-file list, added/removed-line summary, small preview, and the result of `git apply --check --verbose`. Before validation, the command rejects a file outside the workspace, an empty or oversized patch, unsafe target paths, and secret-like material. It does not write audit data or alter the working tree.

## Apply after review

```bash
aiplane patches apply changes.patch --yes
```

Application repeats Git validation immediately before running `git apply --whitespace=error`. It requires all of the following:

- the patch still validates against the current workspace;
- the selected profile permits the `write_file` tool action;
- explicit `--yes` confirmation.

The action is recorded in the local audit log using the patch hash and file count, not the patch content. It never passes `--index`, stages files, creates a commit, or runs arbitrary commands. Check the result before deciding what to do next:

```bash
git diff --check
git diff
git status --short
```

If validation, policy, or confirmation fails, the command returns a JSON status such as `validation_failed`, `policy_blocked`, or `confirmation_required` without applying the patch.

## Scope and recovery

Use a disposable branch or worktree for changes you do not already trust. `aiplane` deliberately does not offer patch generation, conflict resolution, rollback, staging, or commit automation. Use normal Git review and recovery workflows for those actions.
