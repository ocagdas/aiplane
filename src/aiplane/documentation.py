"""Product documentation from this source checkout or the installed distribution.

Never resolve product help from the caller's workspace. Only published documentation
locations are exposed; hidden files and symlinked files/directories are excluded.
"""

from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

DOCUMENT_FILES = (
    "README.md",
    "PURPOSE.md",
    "STATUS.md",
    "VALIDATION.md",
    "ROADMAP.md",
    "TODO.md",
    "CONTRIBUTING.md",
    "CI.md",
    "VERSIONING.md",
    "REPOSITORY_STRUCTURE.md",
    "BRANCHING.md",
    "AGENTS.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
    "NOTICE.md",
    "CHANGELOG.md",
    "docs/index.md",
    "docs/architecture.md",
    "skills/aiplane/SKILL.md",
    "skills/aiplane/agents/openai.yaml",
)
DOCUMENT_DIRECTORIES = (
    "docs/user",
    "docs/development",
    "docs/project",
    "docs/project/trial-evidence",
)


def documentation_root() -> Path:
    source = Path(__file__).resolve().parents[2]
    if (source / "src/aiplane/documentation.py").resolve() == Path(__file__).resolve() and (
        source / "pyproject.toml"
    ).is_file():
        return source
    try:
        installed = distribution("aiplane")
    except PackageNotFoundError as exc:
        raise FileNotFoundError("aiplane documentation is not installed; reinstall the distribution") from exc
    for file in installed.files or ():
        if file.parts[-3:] == ("share", "aiplane", "README.md"):
            return Path(installed.locate_file(file)).resolve().parent
    raise FileNotFoundError("aiplane documentation is missing; reinstall the distribution")


def _published_file(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
        return (
            not any(part.startswith(".") for part in relative.parts)
            and not any(
                parent.is_symlink() for parent in (path, *path.parents) if parent != root and root in parent.parents
            )
            and path.resolve().is_relative_to(root.resolve())
            and path.is_file()
        )
    except (OSError, ValueError):
        return False


def documentation_paths(root: Path) -> list[str]:
    candidates = [root / name for name in DOCUMENT_FILES]
    for directory in DOCUMENT_DIRECTORIES:
        folder = root / directory
        if folder.is_dir() and not folder.is_symlink():
            candidates.extend(folder.glob("*.md"))
    return sorted({path.relative_to(root).as_posix() for path in candidates if _published_file(root, path)})
