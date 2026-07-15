"""Scenario tests for spread and nested toggle detection."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import t_utils as tu
import detectors.nested_detector.nested_detector as nd
import detectors.toggle_match_utils as tmu


class SpreadScenarioTests(unittest.TestCase):
    def test_spread_requires_multiple_files(self):
        toggles = ["FEATURE_ALPHA"]
        with tempfile.TemporaryDirectory() as tmp:
            f1 = os.path.join(tmp, "a.py")
            f2 = os.path.join(tmp, "b.py")
            open(f1, "w").write("def one():\n    if FEATURE_ALPHA:\n        pass\n")
            open(f2, "w").write("def two():\n    return FEATURE_ALPHA\n")
            cfg = os.path.join(tmp, "cfg.py")
            open(cfg, "w").write('FEATURE_ALPHA = "on"\n')
            result = tu.extract_spread_toggles("python", [f1, f2], [cfg])
            self.assertIn("FEATURE_ALPHA", result["toggles"])
            self.assertEqual(len({e["file"] for e in result["toggles"]["FEATURE_ALPHA"]}), 2)

    def test_single_file_not_spread(self):
        toggles = ["ONLY_HERE"]
        with tempfile.TemporaryDirectory() as tmp:
            f1 = os.path.join(tmp, "solo.py")
            open(f1, "w").write("def one():\n    if ONLY_HERE:\n        pass\n")
            cfg = os.path.join(tmp, "cfg.py")
            open(cfg, "w").write('ONLY_HERE = True\n')
            result = tu.extract_spread_toggles("python", [f1], [cfg])
            self.assertNotIn("ONLY_HERE", result["toggles"])

    def test_word_boundary_avoids_substring_false_positive(self):
        line = "if MY_FEATURE_FLAG_EXTRA: pass"
        term_map = tmu.build_term_to_toggle_map(["MY_FEATURE"], {}, None)
        pattern = tmu.build_combined_term_pattern(list(term_map.keys()))
        counts = tmu.count_terms_in_text(line, term_map, pattern)
        self.assertEqual(counts.get("MY_FEATURE", 0), 0)

    def test_alias_definition_line_excluded(self):
        lines = [
            "ALIAS = MY_FEATURE",
            "def run():",
            "    return ALIAS",
        ]
        patterns = tu._compile_alias_patterns("python")
        alias_map, _, excluded = tu._build_file_alias_maps(lines, ["MY_FEATURE"], patterns, "python")
        self.assertIn("MY_FEATURE", alias_map.get("ALIAS", set()))
        term_map = tmu.build_term_to_toggle_map(["MY_FEATURE"], alias_map, None)
        pattern = tmu.build_combined_term_pattern(list(term_map.keys()))
        counts = tmu.count_terms_in_text(
            "\n".join(lines[1:]),
            term_map,
            pattern,
            excluded_by_toggle=excluded,
        )
        self.assertGreaterEqual(counts.get("MY_FEATURE", 0), 1)


class NestedScenarioTests(unittest.TestCase):
    def test_same_line_and_or(self):
        content = "def fn():\n    if ALPHA and BETA:\n        pass\n"
        toggles = ["ALPHA", "BETA"]
        data = nd.process_code_files("python", ["sample.py"], [content], toggles)
        nested = data["nested_toggles"]
        self.assertIn("ALPHA", nested)
        deps = nested["BETA"]["sample.py"]["fn"]["dependencies"]
        self.assertIn("ALPHA", deps)

    def test_structural_nested_if(self):
        content = (
            "def fn():\n"
            "    if OUTER:\n"
            "        if INNER:\n"
            "            pass\n"
        )
        toggles = ["OUTER", "INNER"]
        data = nd.process_code_files("python", ["sample.py"], [content], toggles)
        nested = data["nested_toggles"]
        self.assertIn("OUTER", nested)
        deps = nested["OUTER"]["sample.py"]["fn"]["dependencies"]
        self.assertIn("INNER", deps)

    def test_same_toggle_outer_inner_not_nested(self):
        content = (
            "def fn():\n"
            "    if SAME:\n"
            "        if SAME:\n"
            "            pass\n"
        )
        toggles = ["SAME"]
        data = nd.process_code_files("python", ["sample.py"], [content], toggles)
        nested = data["nested_toggles"]
        self.assertNotIn("SAME", nested)

    def test_string_literal_ignored(self):
        line = 'msg = "ALPHA and BETA"'
        term_map = tmu.build_term_to_toggle_map(["ALPHA", "BETA"], {}, None)
        pattern = tmu.build_combined_term_pattern(list(term_map.keys()))
        found = nd._extract_line_toggles(line, pattern, set(term_map.values()), {}, term_map)
        self.assertEqual(found, set())


if __name__ == "__main__":
    unittest.main()
