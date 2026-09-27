"""Evidence-calibrated modelling and aggregate-carbon regression tests."""

from copy import deepcopy
import csv
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from routing.model import Network, carbon_cost, solve_exact, solve_state_dijkstra
from routing.native_ga import solve_native_ga
from routing.portfolio import aggregate_portfolio, optimize_homogeneous_portfolio
from routing.real_world import direct_corridor_config, historical_progressive_schedule, load_benchmarks


ROOT = Path(__file__).resolve().parents[1]


class EvidenceDataTests(unittest.TestCase):
    def test_every_observation_has_a_source_and_boundary(self):
        data = load_benchmarks()
        ids = {row["id"] for row in data["sources"]}
        self.assertIn("MEE_FACTORS_2025", ids)
        for corridor in data["corridors"]:
            for route in corridor["route_options"]:
                self.assertTrue(set(route["source_ids"]) <= ids)
                self.assertIn("evidence_class", route)
        scope = json.loads((ROOT / "data" / "carbon_price_scenarios.json").read_text())["legal_boundary"]
        self.assertIn("not a claim", scope)

    def test_chongqing_lane_quotes_and_times_are_not_tonne_km_repriced(self):
        network = Network(direct_corridor_config(payload_tonnes=15, deadline_hours=360))
        options = {network.edges[route[0]]["id"]: network.evaluate(route)
                   for route in network.routes()}
        self.assertEqual(options["cq-sh-road"]["scenarios"][0]["transport_cost_cny"], 15000)
        self.assertEqual(options["cq-sh-rail"]["scenarios"][0]["arrival_hours"], 57.5)
        self.assertEqual(options["cq-sh-water-regular"]["scenarios"][0]["arrival_hours"], 240)
        self.assertAlmostEqual(options["cq-sh-rail"]["scenarios"][0]["emissions_kg"], 1733 * 15 * 0.003)

    def test_payload_changes_emissions_but_not_one_container_quote(self):
        low = solve_exact(Network(direct_corridor_config(payload_tonnes=10, deadline_hours=60)))["solution"]
        high = solve_exact(Network(direct_corridor_config(payload_tonnes=20, deadline_hours=60)))["solution"]
        self.assertEqual(low["scenarios"][0]["transport_cost_cny"], high["scenarios"][0]["transport_cost_cny"])
        self.assertAlmostEqual(high["scenarios"][0]["emissions_kg"], 2 * low["scenarios"][0]["emissions_kg"])

    def test_hard_deadlines_switch_available_service(self):
        tight = solve_exact(Network(direct_corridor_config(deadline_hours=48)))["solution"]
        rail = solve_exact(Network(direct_corridor_config(deadline_hours=60)))["solution"]
        express = solve_exact(Network(direct_corridor_config(deadline_hours=216)))["solution"]
        regular = solve_exact(Network(direct_corridor_config(deadline_hours=240)))["solution"]
        self.assertIsNone(tight)
        self.assertEqual([rail["modes"], express["modes"], regular["modes"]],
                         [["rail"], ["water"], ["water"]])
        self.assertEqual([rail["edge_indices"], express["edge_indices"], regular["edge_indices"]],
                         [[1], [2], [3]])

    def test_graph_heuristic_uses_lane_quotes_and_preserves_fast_parallel_service(self):
        express = solve_state_dijkstra(Network(direct_corridor_config(deadline_hours=216)))
        regular = solve_state_dijkstra(Network(direct_corridor_config(deadline_hours=240)))
        self.assertEqual(express["solution"]["edge_indices"], [2])
        self.assertEqual(regular["solution"]["edge_indices"], [3])
        self.assertEqual(express["solution"]["scenarios"][0]["transport_cost_cny"], 1400)

    def test_published_experiment_is_complete_and_visualized(self):
        directory = ROOT / "benchmarks" / "real-case-sensitivity"
        report = json.loads((directory / "results.json").read_text())
        self.assertEqual(report["grid"]["rows"], 1188)
        self.assertEqual(report["algorithm_experiment"]["scenario_count"], 15)
        self.assertEqual(report["algorithm_experiment"]["seeds"], 30)
        with (directory / "algorithm-runs.csv").open() as stream:
            self.assertEqual(sum(1 for _ in csv.DictReader(stream)), 2250)
        for name in ("deadline-carbon-phase.svg", "cost-components.svg",
                     "cost-emissions-frontier.svg", "portfolio-carbon-brackets.svg",
                     "algorithm-quality.svg", "route-tight.svg",
                     "route-balanced.svg", "route-green-stress.svg"):
            self.assertTrue(ET.parse(directory / name).getroot().tag.endswith("svg"))


class PortfolioCarbonTests(unittest.TestCase):
    def test_aggregate_schedule_is_not_reset_per_shipment(self):
        network = Network(direct_corridor_config(deadline_hours=360))
        network.brackets = [(row["lower_bound_kg"], row["rate_cny_per_kg"])
                            for row in historical_progressive_schedule()]
        water = network.evaluate((3,))
        count = 250
        aggregate = aggregate_portfolio([water] * count, network.brackets)
        reset_cost = count * water["scenarios"][0]["carbon_cost_cny"]
        self.assertGreater(aggregate["carbon_cost_cny"], reset_cost)
        self.assertAlmostEqual(aggregate["carbon_cost_cny"], carbon_cost(
            count * water["scenarios"][0]["emissions_kg"], network.brackets))

    def test_portfolio_optimizer_accounts_for_marginal_brackets(self):
        network = Network(direct_corridor_config(deadline_hours=360))
        network.brackets = [(row["lower_bound_kg"], row["rate_cny_per_kg"])
                            for row in historical_progressive_schedule()]
        result = optimize_homogeneous_portfolio(
            [network.evaluate(route) for route in network.routes()], 50, network.brackets)
        self.assertEqual(result["status"], "optimal-enumeration")
        self.assertEqual(sum(result["solution"]["counts"]), 50)

    def test_native_hybrid_reports_preprocessing_cost(self):
        network = Network(direct_corridor_config(deadline_hours=240))
        result = solve_native_ga(network, population=8, generations=4, heuristic_seed=True)
        self.assertEqual(result["candidate_evaluations"], 32)
        self.assertGreater(result["preprocessing_expanded_states"], 0)
        self.assertEqual(result["solver"], "native-priority-ga-hybrid-seeded")


if __name__ == "__main__":
    unittest.main()
