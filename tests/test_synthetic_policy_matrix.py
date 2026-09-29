"""Tests for the policy-calibrated synthetic 23-city experiment."""

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from routing.synthetic import generate_network
from tools.run_synthetic_policy_matrix import (POLICY_VARIANTS, build_instance,
                                               generate_policy_portfolio)


ROOT = Path(__file__).resolve().parents[1]


class SyntheticPolicyMatrixTests(unittest.TestCase):
    def test_policy_controls_are_tuned_on_seeds_disjoint_from_formal_runs(self):
        design = json.loads(
            (ROOT / "data" / "policy_experiment.json").read_text(encoding="utf-8"))
        selection = design["synthetic_23city_extension"]["ga_hyperparameter_selection"]
        tuning = set(selection["tuning_seeds"])
        validation = set(selection["validation_seeds"])
        formal = set(selection["formal_report_seeds"])
        self.assertFalse(tuning & validation)
        self.assertFalse(tuning & formal)
        self.assertFalse(validation & formal)
        self.assertEqual(POLICY_VARIANTS["adaptive"]["mutation_base"], .75)
        self.assertEqual(POLICY_VARIANTS["adaptive"]["mutation_cap"], 1.25)
        self.assertEqual(POLICY_VARIANTS["combined"]["mutation_base"], .5)
        self.assertEqual(POLICY_VARIANTS["combined"]["mutation_cap"], 1.0)
        self.assertEqual(POLICY_VARIANTS["combined"]["patience"], 12)
        self.assertEqual(POLICY_VARIANTS["combined"]["restart_fraction"], .1)

    def test_portfolio_uses_od_and_cargo_specific_48_60_72_hour_deadlines(self):
        design = json.loads(
            (ROOT / "data" / "policy_experiment.json").read_text(encoding="utf-8"))
        nodes = generate_network(23, .1, 42)["nodes"]
        orders = generate_policy_portfolio(nodes, design, "central", "balanced")
        self.assertEqual(len(orders), 48)
        self.assertTrue({row["tonnes"] for row in orders}.issubset(
            set(design["payload_tonnes"])))
        self.assertTrue({row["release_hour"] for row in orders}.issubset(
            set(design["release_hours"])))
        deadline_model = design["synthetic_23city_extension"][
            "operational_time_model"]["deadline_model"]
        self.assertTrue({row["deadline_hours"] - row["release_hour"] for row in orders}.issubset(
            set(deadline_model["lead_time_values_hours"])))
        self.assertEqual({row["cargo_type"] for row in orders},
                         set(deadline_model["cargo_mix"]))
        self.assertTrue({row["od_distance_band"] for row in orders}.issubset(
            {"short", "medium", "long"}))

    def test_water_uses_timed_scarce_departures_and_explicit_delay_components(self):
        design = json.loads(
            (ROOT / "data" / "policy_experiment.json").read_text(encoding="utf-8"))
        network = design["synthetic_23city_extension"]["network"]
        base = generate_network(network["nodes"], network["density"], network["seed"])
        config, generated = build_instance(
            base, design, "central", "balanced", 97.49,
            top_k=6, candidate_routes=30, beam_width=100)
        water_departures = [row for row in generated["departures"]
                            if "-water-H" in row["departure_id"]]
        self.assertTrue(water_departures)
        self.assertTrue(all(not row["capacity_only"] for row in water_departures))
        self.assertEqual({row["capacity_tonnes"] for row in water_departures}, {20.0})
        self.assertEqual({row["capacity_units"] for row in water_departures}, {2.0})
        water_edges = [row for row in config["edges"] if row["mode"] == "water"]
        self.assertTrue(all(row["handling_hours"] > 0 for row in water_edges))
        self.assertTrue(all(row["port_dwell_hours"] > 0 for row in water_edges))
        self.assertTrue(all(row["lock_delay_hours"] > 0 for row in water_edges))
        self.assertTrue(all(row["reliability_buffer_hours"] > 0 for row in water_edges))

    def test_quick_matrix_combines_policy_targets_scopes_and_five_ga_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            subprocess.run([
                sys.executable, "-B",
                str(ROOT / "tools" / "run_synthetic_policy_matrix.py"),
                "--output", str(output),
                "--demands", "central", "--time-profiles", "balanced",
                "--carbon-prices", "97.49", "--reduction-targets", "0,0.2",
                "--formal-targets", "0,0.2", "--screening-seeds", "70",
                "--formal-seeds", "0", "--screening-population", "8",
                "--screening-generations", "2", "--formal-population", "8",
                "--formal-generations", "2", "--candidate-routes", "12",
                "--beam-width", "40", "--top-k", "4", "--workers", "1",
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            report = json.loads((output / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(report["data_classification"],
                             "policy_calibrated_synthetic")
            self.assertEqual(report["screening"]["rows"], 2)
            self.assertEqual(len(report["formal_comparison"]["scenarios"]), 6)
            self.assertEqual(report["formal_comparison"]["runs"], 30)
            self.assertEqual(report["formal_comparison"]["methods"], [
                "fixed", "adaptive", "catastrophe", "combined", "hybrid-seeded"])
            self.assertEqual(report["formal_comparison"]["transport_scopes"], [
                "road-only", "single-mode-per-order", "multimodal-enabled"])
            self.assertTrue(all(
                row["baseline_definition"] ==
                "per_order_minimum_cost_single_trunk_mode_same_scenario"
                for row in report["formal_comparison"]["scenarios"]))
            self.assertEqual(
                {row["baseline_transport_scope"]
                 for row in report["formal_comparison"]["scenarios"]},
                {"single-mode-per-order"})
            self.assertEqual(
                len({row["baseline_emissions_kg"]
                     for row in report["formal_comparison"]["scenarios"]}), 1)
            self.assertEqual(
                report["emissions_target_reference"]["optimality_status"],
                "per-order-candidate-minimum-certified")
            self.assertFalse(
                report["emissions_target_reference"]["shared_capacity_in_reference"])
            with (output / "formal-runs.csv").open(encoding="utf-8") as stream:
                formal_rows = list(csv.DictReader(stream))
            self.assertEqual(len(formal_rows), 30)
            self.assertTrue(any(float(row["reduction_target"]) > 0
                                for row in formal_rows))
            for name in ("screening-grid.csv", "formal-runs.csv",
                         "method-scenario-summary.csv", "README.md",
                         "policy-screening-sensitivity.svg",
                         "scope-ga-cost-time.svg"):
                self.assertTrue((output / name).is_file(), name)
            ET.parse(output / "policy-screening-sensitivity.svg")
            ET.parse(output / "scope-ga-cost-time.svg")


if __name__ == "__main__":
    unittest.main()
