"""Tests for the corridor policy-allocation experiment."""

import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from routing.allocation import evaluate_assignment
from tools.run_policy_allocation_experiment import build_instance, generate_orders


ROOT = Path(__file__).resolve().parents[1]


class PolicyAllocationExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = json.loads(
            (ROOT / "data/policy_experiment.json").read_text(encoding="utf-8"))

    def test_demand_and_time_profiles_generate_deterministic_model_orders(self):
        first = generate_orders(self.design, "central", "balanced")
        second = generate_orders(self.design, "central", "balanced")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 48)
        self.assertTrue(all(row["source_type"] == "deterministic_scenario_order"
                            for row in first))
        self.assertTrue(all(row["deadline_hours"] > row["release_hour"]
                            for row in first))

    def test_corridor_instance_keeps_all_four_route_families(self):
        config, generated = build_instance(
            self.design, "low", "balanced", 97.49)
        self.assertEqual(len(config["nodes"]), 3)
        self.assertEqual(len(generated["orders"]), 24)
        for pool in generated["candidate_pools"].values():
            signatures = {tuple(row["modes"]) for row in pool}
            self.assertEqual(signatures, {("road",), ("rail", "road"), ("water",)})
            self.assertEqual(len(pool), 4)

    def test_emissions_target_is_evaluated_at_portfolio_level(self):
        config, generated = build_instance(
            self.design, "low", "balanced", 97.49)
        chromosome = [0] * len(generated["orders"])
        uncapped = evaluate_assignment(
            generated["orders"], generated["candidate_pools"],
            generated["departures"], chromosome, config["carbon_brackets"])
        capped = evaluate_assignment(
            generated["orders"], generated["candidate_pools"],
            generated["departures"], chromosome, config["carbon_brackets"],
            emission_cap_kg=uncapped["emissions_kg"] * .8)
        self.assertGreater(capped["emission_violation"], 0)
        self.assertFalse(capped["feasible"])

    def test_checked_in_policy_result_has_complete_scope_and_parseable_figures(self):
        output = ROOT / "benchmarks/policy-allocation"
        if not (output / "results.json").exists():
            self.skipTest("generated policy benchmark not checked in yet")
        report = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(report["screening_grid"]["rows"], 108)
        self.assertEqual(report["formal_comparison"]["selected_scenarios"], 12)
        self.assertEqual(report["formal_comparison"]["ga_runs"], 1800)
        frontier = report["central_balanced_current_price_frontier"]
        self.assertEqual([row["reduction_target"] for row in frontier],
                         [0, .095, .2, .3])
        self.assertTrue(all(row["feasible"] for row in frontier))
        for name in ("abatement-frontier.svg", "method-feasibility.svg",
                     "mode-shift.svg", "calibration-context.svg"):
            self.assertTrue(ET.parse(output / name).getroot().tag.endswith("svg"))


if __name__ == "__main__":
    unittest.main()
