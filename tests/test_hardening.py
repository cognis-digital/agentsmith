"""Hardening tests: error paths, edge cases, and input validation."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest

from agentsmith.core import (
    CrewError,
    load_config,
    parse_config,
    scaffold_config,
    to_json,
    validate_crew,
)
from agentsmith.cli import main


class TestLoadConfigErrors(unittest.TestCase):
    """load_config must raise CrewError with a clear message -- never a raw traceback."""

    def test_missing_file_raises_crew_error(self):
        with self.assertRaises(CrewError) as ctx:
            load_config("/nonexistent/path/crew.json")
        self.assertIn("not found", str(ctx.exception))

    def test_malformed_json_raises_crew_error(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write("{not valid json,,}")
            path = fh.name
        try:
            with self.assertRaises(CrewError) as ctx:
                load_config(path)
            self.assertIn("invalid JSON", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_empty_path_raises_crew_error(self):
        with self.assertRaises(CrewError):
            load_config("")

    def test_directory_path_raises_crew_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CrewError) as ctx:
                load_config(d)
            msg = str(ctx.exception).lower()
            # should say directory or permission or could not read — anything but traceback
            self.assertTrue(
                "director" in msg or "permission" in msg or "could not read" in msg,
                f"unexpected message: {msg}",
            )


class TestParseConfigEdgeCases(unittest.TestCase):
    def test_whitespace_only_name_rejected(self):
        cfg = {"name": "   ", "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "a"}]}
        with self.assertRaises(CrewError) as ctx:
            parse_config(cfg)
        self.assertIn("name", str(ctx.exception))

    def test_non_string_name_rejected(self):
        cfg = {"name": 42, "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "a"}]}
        with self.assertRaises(CrewError):
            parse_config(cfg)

    def test_self_dependency_detected(self):
        cfg = {
            "name": "self-dep",
            "agents": [{"id": "a"}],
            "tasks": [{"id": "x", "agent": "a", "depends_on": ["x"]}],
        }
        errs = validate_crew(parse_config(cfg))
        self.assertTrue(any("itself" in e for e in errs))

    def test_agent_illegal_chars_rejected(self):
        cfg = {"name": "n", "agents": [{"id": "bad id!"}], "tasks": [{"id": "x", "agent": "bad id!"}]}
        with self.assertRaises(CrewError) as ctx:
            parse_config(cfg)
        self.assertIn("illegal characters", str(ctx.exception))


class TestScaffoldConfig(unittest.TestCase):
    def test_empty_name_raises(self):
        with self.assertRaises(CrewError):
            scaffold_config("")

    def test_whitespace_name_raises(self):
        with self.assertRaises(CrewError):
            scaffold_config("   ")

    def test_non_string_name_raises(self):
        with self.assertRaises(CrewError):
            scaffold_config(None)  # type: ignore[arg-type]

    def test_valid_name_works(self):
        cfg = scaffold_config("my-crew")
        self.assertEqual(cfg["name"], "my-crew")


class TestToJson(unittest.TestCase):
    def test_basic_dict(self):
        result = to_json({"a": 1})
        self.assertEqual(json.loads(result), {"a": 1})

    def test_non_serialisable_falls_back_to_str(self):
        import datetime
        result = to_json({"ts": datetime.datetime(2024, 1, 1)})
        data = json.loads(result)
        self.assertIsInstance(data["ts"], str)


class TestCLIHardening(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_missing_file_returns_1(self):
        code = main(["validate", os.path.join(self.dir, "no-such.json")])
        self.assertEqual(code, 1)

    def test_malformed_json_returns_1(self):
        path = self._write("bad.json", "{broken}")
        code = main(["run", path])
        self.assertEqual(code, 1)

    def test_malformed_json_returns_1_json_format(self):
        path = self._write("bad.json", "{broken}")
        code = main(["--format", "json", "validate", path])
        self.assertEqual(code, 1)

    def test_init_empty_name_returns_1(self):
        # scaffold_config raises CrewError for empty name -> cli returns 1
        code = main(["init", ""])
        self.assertEqual(code, 1)

    def test_no_command_returns_2(self):
        self.assertEqual(main([]), 2)

    def test_valid_run_still_works(self):
        good = {
            "name": "test",
            "agents": [{"id": "a"}],
            "tasks": [{"id": "x", "agent": "a", "prompt": "do it"}],
        }
        path = self._write("good.json", json.dumps(good))
        self.assertEqual(main(["run", path]), 0)


class TestMcpServerImport(unittest.TestCase):
    def test_mcp_server_imports_cleanly(self):
        """mcp_server must import without error (no broken scan/to_json refs)."""
        import importlib
        mod = importlib.import_module("agentsmith.mcp_server")
        self.assertTrue(callable(mod.serve))


class TestWebhookHardening(unittest.TestCase):
    """Webhook integration: empty stdin and bad URL should exit non-zero."""

    def _run_webhook(self, argv, stdin_text: str) -> int:
        import importlib.util
        import types
        # Load webhook module fresh
        spec = importlib.util.spec_from_file_location(
            "webhook",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "integrations", "webhook.py"),
        )
        assert spec and spec.loader
        mod = types.ModuleType("webhook")
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        old_argv = sys.argv
        old_stdin = sys.stdin
        old_stderr = sys.stderr
        try:
            sys.argv = ["webhook.py"] + argv
            sys.stdin = io.StringIO(stdin_text)
            sys.stderr = io.StringIO()
            return mod.main()
        finally:
            sys.argv = old_argv
            sys.stdin = old_stdin
            sys.stderr = old_stderr

    def test_empty_stdin_returns_1(self):
        code = self._run_webhook(["--url", "https://example.com/hook"], "")
        self.assertEqual(code, 1)

    def test_whitespace_only_stdin_returns_1(self):
        code = self._run_webhook(["--url", "https://example.com/hook"], "   \n  ")
        self.assertEqual(code, 1)

    def test_bad_url_scheme_returns_1(self):
        code = self._run_webhook(["--url", "ftp://example.com/hook"], '{"ok": true}')
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
