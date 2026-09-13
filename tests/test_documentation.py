from pathlib import Path

import pytest

from aiplane import __version__
from aiplane.documentation import documentation_paths, documentation_root
from aiplane.mcp import AiplaneMcpServer


def test_product_help_is_independent_of_workspace(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("unrelated workspace", encoding="utf-8")
    server = AiplaneMcpServer(tmp_path)
    paths = {row["path"] for row in server._doc_index()}
    assert {
        "STATUS.md",
        "docs/architecture.md",
        "docs/development/setup.md",
        "skills/aiplane/agents/openai.yaml",
    } <= paths
    expected = (documentation_root() / "README.md").read_text(encoding="utf-8")
    result = server._read_doc("README.md", 5, 21)
    assert result["content"] == expected[5:26]
    assert result["truncated"]
    response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response["result"]["serverInfo"]["version"] == __version__


@pytest.mark.parametrize(
    "path", ["../README.md", "/etc/passwd", "docs/../README.md", "docs/project/.strategy/private.md", "credentials.md"]
)
def test_docs_reject_unlisted_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError, match="unknown doc path"):
        AiplaneMcpServer(tmp_path)._read_doc(path, 0, 100)


def test_document_index_excludes_private_and_symlinked_files(tmp_path: Path) -> None:
    root = tmp_path / "product"
    (root / "docs/user").mkdir(parents=True)
    (root / "docs/project/.strategy").mkdir(parents=True)
    (root / "README.md").write_text("public", encoding="utf-8")
    (root / "docs/user/.private.md").write_text("private", encoding="utf-8")
    (root / "docs/project/.strategy/private.md").write_text("private", encoding="utf-8")
    assert documentation_paths(root) == ["README.md"]
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.md").write_text("private", encoding="utf-8")
    try:
        (root / "docs/user/link.md").symlink_to(outside / "private.md")
        (root / "docs/development").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    assert documentation_paths(root) == ["README.md"]


def test_provider_http_metadata_uses_application_version() -> None:
    from aiplane.providers import _text_get
    from tests.boundary_fakes import FakeHttpTransport

    transport = FakeHttpTransport({"data": []})
    _text_get("https://provider.example/v1/models", transport=transport)
    request, _timeout = transport.requests[0]
    assert request.get_header("User-agent") == f"aiplane/{__version__}"


def test_installed_documentation_uses_distribution_record(tmp_path: Path, monkeypatch) -> None:
    from importlib.metadata import PackagePath
    from types import SimpleNamespace
    import aiplane.documentation as documentation

    monkeypatch.setattr(documentation, "__file__", str(tmp_path / "lib/site-packages/aiplane/documentation.py"))
    installed_root = tmp_path / "user/share/aiplane"
    record = PackagePath("../../../share/aiplane/README.md")
    monkeypatch.setattr(
        documentation,
        "distribution",
        lambda name: SimpleNamespace(files=[record], locate_file=lambda file: installed_root / "README.md"),
    )
    assert documentation.documentation_root() == installed_root
    monkeypatch.setattr(documentation, "distribution", lambda name: SimpleNamespace(files=[]))
    with pytest.raises(FileNotFoundError, match="reinstall"):
        documentation.documentation_root()
