"""Smoke + behavior tests for AGENTSMITH (stdlib unittest, no network)."""
import json
import os
import tempfile
import unittest

from agentsmith import (
    TOOL_NAME,
    TOOL_VERSION,
    CrewError,
    parse_config,
    plan_crew,
    run_crew,
    scaffold_config,
    validate_crew,
)
from agentsmith.cli import main


GOOD = {
    "name": "t",
    "agents": [{"id": "a"}, {"id": "b"}],
    "tasks": [
        {"id": "x", "agent": "a", "prompt": "start"},
        {"id": "y", "agent": "b", "prompt": "use {{x}}", "depends_on": ["x"]},
    ],
}


class TestCore(unittest.TestCase):
    def test_meta(self):
        self.assertEqual(TOOL_NAME, "agentsmith")
        self.assertTrue(TOOL_VERSION)

    def test_scaffold_is_valid_and_runs(self):
        crew = parse_config(scaffold_config())
        self.assertEqual(validate_crew(crew), [])
        report = run_crew(crew)
        self.assertEqual(report["tasks"], 2)
        self.assertIsNotNone(report["final"])

    def test_plan_waves(self):
        crew = parse_config(GOOD)
        self.assertEqual(plan_crew(crew), [["x"], ["y"]])

    def test_parallel_wave(self):
        cfg = {
            "name": "p",
            "agents": [{"id": "a"}],
            "tasks": [
                {"id": "root", "agent": "a"},
                {"id": "l", "agent": "a", "depends_on": ["root"]},
                {"id": "r", "agent": "a", "depends_on": ["root"]},
            ],
        }
        waves = plan_crew(parse_config(cfg))
        self.assertEqual(waves, [["root"], ["l", "r"]])
        self.assertEqual(max(len(w) for w in waves), 2)

    def test_dataflow_renders(self):
        report = run_crew(parse_config(GOOD))
        ystep = [s for s in report["steps"] if s["task"] == "y"][0]
        self.assertIn("[a] x::", ystep["prompt"])  # x output flowed into y
        self.assertNotIn("{{x}}", ystep["prompt"])

    def test_deterministic(self):
        a = run_crew(parse_config(GOOD))["final"]
        b = run_crew(parse_config(GOOD))["final"]
        self.assertEqual(a, b)

    def test_cycle_detected(self):
        cfg = {
            "name": "c",
            "agents": [{"id": "a"}],
            "tasks": [
                {"id": "x", "agent": "a", "depends_on": ["y"]},
                {"id": "y", "agent": "a", "depends_on": ["x"]},
            ],
        }
        errs = validate_crew(parse_config(cfg))
        self.assertTrue(any("cycle" in e for e in errs))
        with self.assertRaises(CrewError):
            plan_crew(parse_config(cfg))

    def test_unknown_agent(self):
        cfg = {"name": "u", "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "ghost"}]}
        errs = validate_crew(parse_config(cfg))
        self.assertTrue(any("unknown agent" in e for e in errs))

    def test_unknown_dep(self):
        cfg = {"name": "u", "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "a", "depends_on": ["nope"]}]}
        errs = validate_crew(parse_config(cfg))
        self.assertTrue(any("unknown task" in e for e in errs))

    def test_dangling_placeholder(self):
        cfg = {"name": "d", "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "a", "prompt": "{{missing}}"}]}
        errs = validate_crew(parse_config(cfg))
        self.assertTrue(any("missing" in e for e in errs))

    def test_duplicate_ids(self):
        cfg = {"name": "d", "agents": [{"id": "a"}, {"id": "a"}], "tasks": [{"id": "x", "agent": "a"}]}
        errs = validate_crew(parse_config(cfg))
        self.assertTrue(any("duplicate agent" in e for e in errs))

    def test_bad_config_shape(self):
        with self.assertRaises(CrewError):
            parse_config({"name": "x", "agents": [], "tasks": []})


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.good = os.path.join(self.dir, "good.json")
        with open(self.good, "w", encoding="utf-8") as fh:
            json.dump(GOOD, fh)
        self.bad = os.path.join(self.dir, "bad.json")
        with open(self.bad, "w", encoding="utf-8") as fh:
            json.dump({"name": "b", "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "ghost"}]}, fh)

    def test_validate_ok(self):
        self.assertEqual(main(["validate", self.good]), 0)

    def test_validate_fail_nonzero(self):
        self.assertEqual(main(["--format", "json", "validate", self.bad]), 1)

    def test_plan_json(self):
        self.assertEqual(main(["--format", "json", "plan", self.good]), 0)

    def test_run_ok(self):
        self.assertEqual(main(["run", self.good]), 0)

    def test_init(self):
        self.assertEqual(main(["init", "my-crew"]), 0)

    def test_missing_file_nonzero(self):
        self.assertEqual(main(["validate", os.path.join(self.dir, "nope.json")]), 1)

    def test_no_command_returns_2(self):
        self.assertEqual(main([]), 2)


if __name__ == "__main__":
    unittest.main()
