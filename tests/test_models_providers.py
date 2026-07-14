from __future__ import annotations

from .support import (
    ModelCatalog,
    Path,
    StringIO,
    _isolated_test_profile,
    cli_main,
    load_profile,
    redirect_stdout,
    unittest,
)


class ModelProviderTests(unittest.TestCase):
    def test_models_help_lists_clear_cache_command(self) -> None:
        stdout = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stdout(stdout):
                cli_main(["models", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("clear-cache", stdout.getvalue())

    def test_model_catalog_lists_default_models(self) -> None:
        profile = load_profile("local-dev", Path.cwd())
        rows = ModelCatalog(profile).list()
        names = {row["name"] for row in rows}
        self.assertIn("fixture-analysis-small", names)
        self.assertNotIn("openai-main", names)
        self.assertIn("local-reasoning-xl", names)
        self.assertIn("codelocal-chat-large", names)
        analysis_model = next(row for row in rows if row["name"] == "fixture-analysis-small")
        self.assertIn("capabilities", analysis_model)
        self.assertEqual(analysis_model["capabilities"]["score_scale"], "0-5")
        self.assertIn("code_generation", analysis_model["capabilities"]["scores"])

    def test_continue_visible_ollama_models_have_catalog_roles(self) -> None:
        with _isolated_test_profile() as profile:
            catalog = ModelCatalog(profile)

            llama = catalog.show("fixture-chat-small")
            self.assertEqual(llama["model"], "provider-chat-small:8b")
            self.assertIn("chat", llama["roles"])

            code_base = catalog.show("fixture-code-base")
            self.assertEqual(code_base["model"], "provider-code-base:1.5b")
            self.assertIn("autocomplete", code_base["roles"])
            self.assertGreaterEqual(code_base["capabilities"]["scores"]["code_completion"], 3)

            embedding_row = catalog.show("fixture-embedding-small")
            self.assertEqual(embedding_row["model"], "fixture-embedding-small:latest")
            self.assertIn("embedding", embedding_row["roles"])
            self.assertEqual(embedding_row["capabilities"]["scores"]["embedding"], 5)

            autocomplete_rows = catalog.filter({"role": "autocomplete"})
            self.assertIn("fixture-code-base", {row["name"] for row in autocomplete_rows})
            embedding_rows = catalog.filter({"role": "embedding"})
            self.assertIn("fixture-embedding-small", {row["name"] for row in embedding_rows})
