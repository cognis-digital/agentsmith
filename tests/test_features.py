"""Behavior tests for the analysis + export features of AGENTSMITH.

Covers the additive capabilities layered on top of the core engine:
critical-path analysis, crew metrics, DOT / Mermaid export, the MCP-facing
``scan`` entrypoint, and the ``stats`` / ``graph`` CLI subcommands. Every test
asserts on real, computed behavior -- no placeholders.
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from agentsmith import (
    CrewError,
    critical_path,
    describe_crew,
    parse_config,
    scaffold_config,
    scan,
    to_dot,
    to_json,
    to_mermaid,
)
from agentsmith.cli import main


# A diamond DAG: root -> {left, right} -> join, plus a longer tail so the
# critical path is unambiguous and longer than the widest wave.
DIAMOND = {
    "name": "diamond",
    "agents": [{"id": "a"}, {"id": "b"}],
    "tasks": [
        {"id": "root", "agent": "a", "prompt": "seed"},
        {"id": "left", "agent": "a", "prompt": "L {{root}}", "depends_on": ["root"]},
        {"id": "right", "agent": "b", "prompt": "R {{root}}", "depends_on": ["root"]},
        {
            "id": "join",
            "agent": "b",
            "prompt": "J {{left}} {{right}}",
            "depends_on": ["left", "right"],
        },
        {"id": "tail", "agent": "a", "prompt": "T {{join}}", "depends_on": ["join"]},
    ],
}


class TestCriticalPath(unittest.TestCase):
    def test_linear_chain_is_whole_chain(self):
        cfg = {
            "name": "line",
            "agents": [{"id": "a"}],
            "tasks": [
                {"id": "s1", "agent": "a"},
                {"id": "s2", "agent": "a", "depends_on": ["s1"]},
                {"id": "s3", "agent": "a", "depends_on": ["s2"]},
            ],
        }
        self.assertEqual(critical_path(parse_config(cfg)), ["s1", "s2", "s3"])

    def test_diamond_longest_chain(self):
        cp = critical_path(parse_config(DIAMOND))
        # length is 4 (root -> side -> join -> tail), not the 5 total tasks
        self.assertEqual(len(cp), 4)
        self.assertEqual(cp[0], "root")
        self.assertEqual(cp[-1], "tail")
        self.assertIn(cp[1], {"left", "right"})
        self.assertEqual(cp[2], "join")

    def test_single_task_path(self):
        cfg = {"name": "one", "agents": [{"id": "a"}], "tasks": [{"id": "only", "agent": "a"}]}
        self.assertEqual(critical_path(parse_config(cfg)), ["only"])

    def test_deterministic(self):
        crew = parse_config(DIAMOND)
        self.assertEqual(critical_path(crew), critical_path(crew))

    def test_raises_on_cycle(self):
        cfg = {
            "name": "c",
            "agents": [{"id": "a"}],
            "tasks": [
                {"id": "x", "agent": "a", "depends_on": ["y"]},
                {"id": "y", "agent": "a", "depends_on": ["x"]},
            ],
        }
        with self.assertRaises(CrewError):
            critical_path(parse_config(cfg))


class TestDescribeCrew(unittest.TestCase):
    def test_diamond_metrics(self):
        info = describe_crew(parse_config(DIAMOND))
        self.assertEqual(info["crew"], "diamond")
        self.assertEqual(info["tasks"], 5)
        self.assertEqual(info["agents"], 2)
        self.assertEqual(info["edges"], 5)  # left,right,join(x2),tail
        self.assertEqual(info["roots"], ["root"])
        self.assertEqual(info["leaves"], ["tail"])
        self.assertEqual(info["max_parallel"], 2)  # left + right run together
        self.assertEqual(info["critical_path_length"], 4)
        self.assertEqual(info["tasks_per_agent"], {"a": 3, "b": 2})

    def test_roots_and_leaves_multiple(self):
        cfg = {
            "name": "multi",
            "agents": [{"id": "a"}],
            "tasks": [
                {"id": "r1", "agent": "a"},
                {"id": "r2", "agent": "a"},
                {"id": "j", "agent": "a", "depends_on": ["r1", "r2"]},
                {"id": "l2", "agent": "a", "depends_on": ["r1"]},
            ],
        }
        info = describe_crew(parse_config(cfg))
        self.assertEqual(info["roots"], ["r1", "r2"])
        self.assertEqual(sorted(info["leaves"]), ["j", "l2"])

    def test_tasks_per_agent_sorted(self):
        info = describe_crew(parse_config(scaffold_config()))
        self.assertEqual(list(info["tasks_per_agent"].keys()), sorted(info["tasks_per_agent"].keys()))

    def test_raises_on_invalid(self):
        cfg = {"name": "u", "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "ghost"}]}
        with self.assertRaises(CrewError):
            describe_crew(parse_config(cfg))


class TestDotExport(unittest.TestCase):
    def test_dot_structure(self):
        dot = to_dot(parse_config(DIAMOND))
        self.assertTrue(dot.startswith('digraph "diamond" {'))
        self.assertTrue(dot.rstrip().endswith("}"))
        # one edge line per dependency
        self.assertEqual(dot.count("->"), 5)
        self.assertIn('"root" -> "left";', dot)
        self.assertIn('"join" -> "tail";', dot)

    def test_dot_node_labels_include_agent(self):
        dot = to_dot(parse_config(DIAMOND))
        self.assertIn('"root" [label="root\\n(a)"];', dot)

    def test_dot_escapes_quotes_in_name(self):
        cfg = {
            "name": 'has "quote"',
            "agents": [{"id": "a"}],
            "tasks": [{"id": "x", "agent": "a"}],
        }
        dot = to_dot(parse_config(cfg))
        self.assertIn('digraph "has \\"quote\\"" {', dot)

    def test_dot_renders_even_when_cyclic(self):
        # export is a pure rendering -- it must not require a valid DAG
        cfg = {
            "name": "c",
            "agents": [{"id": "a"}],
            "tasks": [
                {"id": "x", "agent": "a", "depends_on": ["y"]},
                {"id": "y", "agent": "a", "depends_on": ["x"]},
            ],
        }
        dot = to_dot(parse_config(cfg))
        self.assertIn('"y" -> "x";', dot)
        self.assertIn('"x" -> "y";', dot)


class TestMermaidExport(unittest.TestCase):
    def test_mermaid_header_and_nodes(self):
        mmd = to_mermaid(parse_config(DIAMOND))
        self.assertTrue(mmd.startswith("flowchart LR"))
        self.assertEqual(mmd.count("-->"), 5)
        self.assertIn('["root<br/>(a)"]', mmd)

    def test_mermaid_node_keys_are_safe(self):
        # ids with '.' and '-' must not leak into node keys
        cfg = {
            "name": "safe",
            "agents": [{"id": "a"}],
            "tasks": [
                {"id": "a.b", "agent": "a"},
                {"id": "c-d", "agent": "a", "depends_on": ["a.b"]},
            ],
        }
        mmd = to_mermaid(parse_config(cfg))
        self.assertIn('n0["a.b<br/>(a)"]', mmd)
        self.assertIn('n1["c-d<br/>(a)"]', mmd)
        self.assertIn("n0 --> n1", mmd)


class TestScan(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _write(self, name, obj):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        return path

    def test_scan_valid_embeds_summary(self):
        path = self._write("good.json", scaffold_config())
        report = scan(path)
        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], [])
        self.assertIn("critical_path", report)
        self.assertEqual(report["tasks"], 2)

    def test_scan_missing_file(self):
        report = scan(os.path.join(self.dir, "nope.json"))
        self.assertFalse(report["ok"])
        self.assertTrue(any("not found" in e for e in report["errors"]))

    def test_scan_invalid_config_reports_errors(self):
        path = self._write(
            "bad.json",
            {"name": "b", "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "ghost"}]},
        )
        report = scan(path)
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])
        self.assertNotIn("critical_path", report)

    def test_to_json_roundtrips(self):
        report = scan(self._write("g.json", scaffold_config()))
        parsed = json.loads(to_json(report))
        self.assertEqual(parsed["crew"], report["crew"])


class TestExtendedCLI(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg = os.path.join(self.dir, "crew.json")
        with open(self.cfg, "w", encoding="utf-8") as fh:
            json.dump(DIAMOND, fh)

    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(argv)
        return rc, buf.getvalue()

    def test_stats_table(self):
        rc, out = self._run(["stats", self.cfg])
        self.assertEqual(rc, 0)
        self.assertIn("critical path (4)", out)
        self.assertIn("max parallel: 2", out)

    def test_stats_json(self):
        rc, out = self._run(["--format", "json", "stats", self.cfg])
        self.assertEqual(rc, 0)
        obj = json.loads(out)
        self.assertEqual(obj["command"], "stats")
        self.assertEqual(obj["critical_path_length"], 4)

    def test_graph_dot_default(self):
        rc, out = self._run(["graph", self.cfg])
        self.assertEqual(rc, 0)
        self.assertIn("digraph", out)
        self.assertIn("->", out)

    def test_graph_mermaid(self):
        rc, out = self._run(["graph", self.cfg, "--syntax", "mermaid"])
        self.assertEqual(rc, 0)
        self.assertIn("flowchart LR", out)
        self.assertIn("-->", out)

    def test_stats_invalid_config_nonzero(self):
        bad = os.path.join(self.dir, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump({"name": "b", "agents": [{"id": "a"}], "tasks": [{"id": "x", "agent": "ghost"}]}, fh)
        rc, _ = self._run(["stats", bad])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
