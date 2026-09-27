"""Tests for the maintained implementation and its data-boundary guarantees."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from routing.model import Network, solve_state_dijkstra
from routing.native_ga import solve_native_ga
from routing.pipeline import analyze_connectivity, consolidate_orders, plan_orders, write_route_svg
from routing.synthetic import generate_network, generate_orders, historical_profile


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / "examples/synthetic-network.json").read_text())


class HistoricalScaleTests(unittest.TestCase):
    def test_geatpy_runtime_dependencies_are_declared(self):
        dockerfile = (ROOT / "Dockerfile.geatpy").read_text()
        workflow = (ROOT / ".github/workflows/tests.yml").read_text()
        requirements = (ROOT / "requirements-geatpy.txt").read_text()
        self.assertIn("libgomp1", dockerfile)
        self.assertIn("libgomp1", workflow)
        self.assertIn("geatpy-2.7.0-cp310-cp310-manylinux1_x86_64.whl#sha256=", requirements)

    def test_profile_and_23_city_generator(self):
        profile = historical_profile()
        self.assertEqual(profile["base_cities"], 23)
        self.assertEqual(sum(profile["available_mode_distances"].values()), 754)
        config = generate_network()
        self.assertEqual(len(config["nodes"]), 23)
        self.assertEqual(len(config["edges"]), 754)
        self.assertEqual(config["data_classification"], "synthetic_calibrated")
        self.assertEqual(generate_network(), config)

    def test_historical_rate_bands(self):
        network = Network(generate_network())
        self.assertEqual(network.mode_rate("road", 499), 0.263)
        self.assertEqual(network.mode_rate("road", 500), 0.2485)
        self.assertEqual(network.mode_rate("road", 1000), 0.1805)

    def test_saved_scale_benchmark_is_transparently_scoped(self):
        report = json.loads((ROOT / "benchmarks/synthetic_23city_100k_orders_30seeds.json").read_text())
        self.assertEqual(report["data_classification"], "synthetic_calibrated")
        self.assertEqual((report["nodes"], report["edges"], report["orders"]), (23, 754, 100000))
        self.assertIn("not every batch", report["scope"])
        for summary in report["ga_summary"]:
            self.assertEqual(summary["runs"], 30)
        self.assertTrue(all(run["candidate_evaluations"] == 800 for run in report["ga_runs"]))

    def test_real_geatpy_results_are_scoped_and_visualized(self):
        directory = ROOT / "benchmarks/geatpy-23city-ablation"
        report = json.loads((directory / "results.json").read_text())
        self.assertEqual(report["data_classification"], "synthetic_calibrated")
        self.assertEqual((report["network"]["nodes"], report["network"]["edges"]), (23, 754))
        self.assertEqual(len(report["runs"]), 150)
        self.assertEqual({row["variant"] for row in report["summary"]},
                         {"fixed", "adaptive", "catastrophe", "combined", "hybrid-seeded"})
        self.assertIn("not historical orders", report["scope"])
        for name in ("objective-distribution.svg", "convergence.svg",
                     "evaluation-efficiency.svg", "best-route.svg"):
            root = ET.parse(directory / name).getroot()
            self.assertTrue(root.tag.endswith("svg"))


class NativeGATests(unittest.TestCase):
    def test_variants_have_equal_candidate_budget(self):
        network = Network(fixture())
        for adaptive, catastrophe in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(adaptive=adaptive, catastrophe=catastrophe):
                result = solve_native_ga(network, population=20, generations=12, seed=42,
                                         patience=2, adaptive=adaptive, catastrophe=catastrophe)
                self.assertEqual(result["candidate_evaluations"], 240)
                self.assertEqual(len(result["trace"]), 12)
                self.assertIsNotNone(result["solution"])

    def test_catastrophe_preserves_solution_and_is_reproducible(self):
        config = fixture()
        config["edges"] = [config["edges"][2]]
        network = Network(config)
        first = solve_native_ga(network, population=8, generations=7, seed=4, patience=1,
                                adaptive=False, catastrophe=True)
        second = solve_native_ga(network, population=8, generations=7, seed=4, patience=1,
                                 adaptive=False, catastrophe=True)
        self.assertEqual(first, second)
        self.assertGreater(first["restarts"], 0)
        self.assertEqual(first["solution"]["modes"], ["road"])

    def test_fast_state_baseline(self):
        result = solve_state_dijkstra(Network(generate_network()))
        self.assertEqual(result["status"], "feasible-heuristic")
        self.assertEqual(result["solution"]["route"][0], "Chongqing")
        self.assertEqual(result["solution"]["route"][-1], "Shanghai")


class PipelineTests(unittest.TestCase):
    def test_order_generation_validation_and_consolidation(self):
        config = generate_network(node_count=8, density=0.5)
        orders = generate_orders(config["nodes"], 100, 9)
        self.assertTrue(all(row["source_type"] == "synthetic_calibrated" for row in orders))
        batches = consolidate_orders(orders, config["nodes"], max_batch_tonnes=500)
        self.assertAlmostEqual(sum(row["tonnes"] for row in orders), sum(row["tonnes"] for row in batches))
        self.assertTrue(all(row["tonnes"] <= 500 for row in batches))

    def test_full_flow_and_edge_closure(self):
        config = generate_network(node_count=6, density=1, seed=3)
        orders = [{"order_id": "A", "origin": config["origin"], "destination": config["destination"],
                   "tonnes": 40, "deadline_hours": 96, "source_type": "synthetic_calibrated"}]
        result = plan_orders(config, orders, "dijkstra")
        self.assertEqual(result["input_orders"], 1)
        self.assertIsNotNone(result["plans"][0]["routing"]["solution"])
        closed = [edge["id"] for edge in config["edges"] if edge["from"] == config["origin"]]
        blocked = plan_orders(config, orders, "dijkstra", closed_edge_ids=closed)
        self.assertIsNone(blocked["plans"][0]["routing"]["solution"])
        self.assertFalse(blocked["plans"][0]["connectivity"]["destination_reachable"])

    def test_dfs_reachability_and_topological_order(self):
        network = Network(generate_network(node_count=7, density=0.6, seed=4))
        report = analyze_connectivity(network)
        self.assertTrue(report["destination_reachable"])
        self.assertTrue(report["is_dag"])
        positions = {node: index for index, node in enumerate(report["topological_order"])}
        self.assertTrue(all(positions[edge["from"]] < positions[edge["to"]] for edge in network.edges))

    def test_capacity_and_svg_output(self):
        config = generate_network(node_count=5, density=1)
        config["scenarios"] = [{"name": "fixed", "tonnes": 600, "probability": 1,
                                "speed_multiplier": 1, "rate_multiplier": 1}]
        network = Network(config)
        route = network.decode([0] * len(network.edges))
        self.assertFalse(network.evaluate(route)["feasible"])
        normal = Network(generate_network(node_count=5, density=1))
        solution = solve_state_dijkstra(normal)["solution"]
        with tempfile.TemporaryDirectory() as directory:
            path = write_route_svg(normal, solution, Path(directory) / "route.svg")
            rendered = path.read_text(encoding="utf-8")
            self.assertIn("Computed multimodal route", rendered)
            self.assertIn("Shanghai", rendered)

    def test_rejects_unlabelled_orders(self):
        config = generate_network(node_count=5)
        order = {"order_id": "A", "origin": config["origin"], "destination": config["destination"],
                 "tonnes": 20, "deadline_hours": 62, "source_type": "real"}
        with self.assertRaises(ValueError):
            consolidate_orders([order], config["nodes"])


if __name__ == "__main__":
    unittest.main()
