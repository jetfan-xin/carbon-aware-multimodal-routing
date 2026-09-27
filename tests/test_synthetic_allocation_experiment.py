"""End-to-end smoke test for the 23-city allocation stress-test CLI."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


class SyntheticAllocationExperimentTests(unittest.TestCase):
    def test_checked_in_30_seed_result_is_scoped_and_consistent(self):
        output = ROOT / "benchmarks" / "synthetic-global-allocation"
        report = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(report["data_classification"], "synthetic_calibrated")
        self.assertEqual((report["network"]["nodes"], report["portfolio"]["orders"]),
                         (23, 48))
        self.assertEqual(report["exact_oracle"]["candidate_evaluations"], 7776)
        self.assertEqual(report["exact_oracle"]["status"], "optimal")
        self.assertEqual({row["method"] for row in report["method_summary"]},
                         {"greedy", "fixed", "adaptive", "catastrophe",
                          "combined", "hybrid-seeded"})
        self.assertTrue(all(row["feasible_runs"] == row["runs"]
                            for row in report["method_summary"]))
        greedy = next(row for row in report["method_summary"] if row["method"] == "greedy")
        best = report["best_known_full_portfolio"]["solution"]["total_cost_cny"]
        self.assertEqual(report["best_known_full_portfolio"]["method"],
                         "hybrid-seeded")
        self.assertEqual(report["best_known_full_portfolio"]["seed"], 17)
        self.assertAlmostEqual(best, 304051.84844)
        expected = (greedy["best_cost_cny"] - best) / greedy["best_cost_cny"] * 100
        self.assertAlmostEqual(report["best_known_saving_vs_greedy_percent"], expected)
        for name in ("objective-by-method.svg", "convergence.svg",
                     "mode-allocation.svg", "capacity-use.svg"):
            self.assertTrue(ET.parse(output / name).getroot().tag.endswith("svg"))

    def test_small_run_writes_results_and_visualizations(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            subprocess.run([
                sys.executable, "-B", str(ROOT / "tools/run_synthetic_allocation_experiment.py"),
                "--orders", "8", "--seeds", "0", "--population", "8",
                "--generations", "2", "--oracle-orders", "2",
                "--candidate-routes", "12", "--beam-width", "40",
                "--output", str(output),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            report = json.loads((output / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(report["data_classification"], "synthetic_calibrated")
            self.assertEqual(report["network"]["nodes"], 23)
            self.assertEqual(report["portfolio"]["orders"], 8)
            self.assertEqual(report["exact_oracle"]["status"], "optimal")
            self.assertTrue(report["best_known_full_portfolio"]["solution"]["feasible"])
            for name in ("runs.csv", "method-summary.csv", "traces.csv",
                         "best-assignments.csv", "best-capacity.csv",
                         "objective-by-method.svg", "convergence.svg",
                         "mode-allocation.svg", "capacity-use.svg"):
                self.assertTrue((output / name).is_file(), name)

    def test_tuning_and_held_out_validation_are_disjoint_and_consistent(self):
        tuning = json.loads((ROOT / "benchmarks/allocation-control-tuning/results.json")
                            .read_text(encoding="utf-8"))
        validation = json.loads(
            (ROOT / "benchmarks/allocation-control-validation/results.json")
            .read_text(encoding="utf-8"))
        self.assertEqual(tuning["seeds"], list(range(30, 40)))
        self.assertEqual(validation["seeds"], list(range(40, 70)))
        self.assertFalse(set(tuning["seeds"]) & set(validation["seeds"]))
        self.assertEqual(tuning["selected_configuration"], "v2-r25-p30-m3")
        comparisons = {(row["new"], row["baseline"]): row
                       for row in validation["paired_comparisons"]}
        hybrid = comparisons[("selected-hybrid-v2", "legacy-hybrid")]
        self.assertGreater(hybrid["wins"], hybrid["losses"])
        self.assertLess(hybrid["mean_paired_cost_change_cny"], 0)
        self.assertLess(hybrid["approx_95_percent_interval_cny"][1], 0)
        selected = next(row for row in validation["summaries"]
                        if row["configuration"] == "selected-hybrid-v2")
        self.assertEqual(selected["controls"]["adaptive_control"], "diversity-v2")
        self.assertEqual(selected["controls"]["heuristic_seed_mode"], "archive")
        self.assertEqual(selected["controls"]["heuristic_seed_strategy"],
                         "opportunity")


if __name__ == "__main__":
    unittest.main()
