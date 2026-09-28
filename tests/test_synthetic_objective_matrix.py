"""Tests for the 23-city objective and transport-policy matrix."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


class SyntheticObjectiveMatrixTests(unittest.TestCase):
    def test_small_matrix_has_five_methods_and_fixed_reference_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            subprocess.run([
                sys.executable, "-B",
                str(ROOT / "tools/run_synthetic_objective_matrix.py"),
                "--orders", "8", "--seeds", "0", "--population", "8",
                "--generations", "2", "--candidate-routes", "12",
                "--beam-width", "40", "--output", str(output),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            report = json.loads((output / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(report["data_classification"], "synthetic_calibrated")
            self.assertEqual(len(report["scenarios"]), 8)
            self.assertEqual(report["algorithm_budget"]["methods"], [
                "fixed", "adaptive", "catastrophe", "combined", "hybrid-seeded"])
            self.assertEqual(len(report["method_scenario_summary"]), 8 * 5)
            road_emissions = report["reference"]["emissions_kg"]
            scenarios = {row["id"]: row for row in report["scenarios"]}
            self.assertAlmostEqual(
                scenarios["multimodal-reduction-20"]["cap"], road_emissions * .8)
            self.assertAlmostEqual(
                scenarios["multimodal-reduction-55"]["cap"], road_emissions * .45)
            self.assertEqual(scenarios["road-cost"]["scope"], "road-only")
            self.assertEqual(scenarios["single-mode-cost"]["scope"],
                             "single-mode-per-order")
            self.assertEqual(scenarios["multimodal-cost"]["scope"],
                             "multimodal-enabled")
            for name in ("runs.csv", "method-scenario-summary.csv",
                         "scenario-best.csv", "best-assignments.csv",
                         "representative-traces.csv", "cost-emissions-frontier.svg",
                         "five-ga-scenario-matrix.svg"):
                self.assertTrue((output / name).is_file(), name)
            for name in ("cost-emissions-frontier.svg",
                         "five-ga-scenario-matrix.svg"):
                self.assertTrue(ET.parse(output / name).getroot().tag.endswith("svg"))

    def test_checked_in_matrix_is_full_budget_and_self_consistent(self):
        output = ROOT / "benchmarks/synthetic-global-allocation/objective-matrix"
        if not (output / "results.json").is_file():
            self.skipTest("formal objective matrix has not been generated")
        report = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(report["portfolio"]["orders"], 48)
        self.assertEqual(report["network"]["nodes"], 23)
        self.assertEqual(report["algorithm_budget"]["seeds"], list(range(30)))
        self.assertEqual(report["algorithm_budget"]["population"], 100)
        self.assertEqual(report["algorithm_budget"]["generations"], 150)
        self.assertEqual(len(report["method_scenario_summary"]), 40)
        for row in report["method_scenario_summary"]:
            self.assertEqual(row["runs"], 30)
            self.assertLessEqual(row["feasible_runs"], row["runs"])
        road = report["reference"]["emissions_kg"]
        best = {row["scenario"]: row for row in report["best_known_by_scenario"]}
        feasible = [row for row in best.values() if row["feasible"]]
        for row in feasible:
            self.assertAlmostEqual(sum(row[key] for key in (
                "road_only_tonnes", "rail_only_tonnes", "water_only_tonnes",
                "multimodal_tonnes")), report["portfolio"]["tonnes"])
        self.assertLessEqual(best["multimodal-cost"]["total_cost_cny"],
                             best["multimodal-reduction-20"]["total_cost_cny"])
        self.assertLessEqual(best["multimodal-reduction-20"]["total_cost_cny"],
                             best["multimodal-reduction-40"]["total_cost_cny"])
        self.assertEqual(best["multimodal-cost"]["source_scenario"],
                         "multimodal-reduction-40")
        for level in (20, 40, 55, 60):
            row = best[f"multimodal-reduction-{level}"]
            if row["feasible"]:
                self.assertLessEqual(row["emissions_kg"], road * (1-level/100) + 1e-7)


if __name__ == "__main__":
    unittest.main()
