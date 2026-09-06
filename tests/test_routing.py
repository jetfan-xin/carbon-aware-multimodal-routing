"""Routing model tests, independent of historical-result transcription tests."""

from copy import deepcopy
import itertools
import json
from pathlib import Path
import random
import unittest

from routing.model import Network, carbon_cost, solve_exact

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / "examples/synthetic-network.json").read_text())


class CostTests(unittest.TestCase):
    def setUp(self):
        self.c = fixture()
        self.c["scenarios"] = [dict(name="fixed", tonnes=100, probability=1, speed_multiplier=1, rate_multiplier=1)]

    def test_single_mode_hand_calculation(self):
        r = Network(self.c).evaluate((2,))["scenarios"][0]
        self.assertAlmostEqual(r["transport_cost_cny"], 21040)
        self.assertAlmostEqual(r["emissions_kg"], 5680)
        self.assertAlmostEqual(r["total_cost_cny"], 21324)
        self.assertEqual(r["arrival_hours"], 10)
        self.assertEqual(r["transfer_cost_cny"], 0)

    def test_mode_change_hand_calculation(self):
        r = Network(self.c).evaluate((0, 1))["scenarios"][0]
        self.assertAlmostEqual(r["transport_cost_cny"], 8580)
        self.assertEqual(r["transfer_cost_cny"], 250)
        self.assertEqual(r["transfer_hours"], 5)
        self.assertEqual(r["arrival_hours"], 30)
        self.assertAlmostEqual(r["emissions_kg"], 1991.3)
        self.assertAlmostEqual(r["total_cost_cny"], 8929.565)

    def test_no_transfer_for_same_mode(self):
        r = Network(self.c).evaluate((3, 4))["scenarios"][0]
        self.assertEqual(r["transfer_cost_cny"], 0)
        self.assertEqual(r["transfer_emissions_kg"], 0)

    def test_progressive_carbon_boundaries(self):
        brackets = Network(self.c).brackets
        for emission, cost in ((0, 0), (150000, 7500), (150001, 7500.1), (500000, 42500), (1000000, 117500), (1000001, 117500.2)):
            self.assertAlmostEqual(carbon_cost(emission, brackets), cost)

    def test_waiting_and_late_costs(self):
        self.c["time_window_hours"] = [12, 20]
        n = Network(self.c)
        self.assertEqual(n.evaluate((2,))["scenarios"][0]["time_cost_cny"], 3000)
        self.assertEqual(n.evaluate((0, 1))["scenarios"][0]["time_cost_cny"], 30000)

    def test_soft_and_hard_deadlines(self):
        self.c["time_window_hours"] = [0, 20]
        self.assertTrue(Network(self.c).evaluate((0, 1))["feasible"])
        self.c["hard_deadline"] = True
        self.assertFalse(Network(self.c).evaluate((0, 1))["feasible"])
        self.assertTrue(Network(self.c).evaluate((2,))["feasible"])

    def test_emission_cap_applies_to_every_scenario(self):
        self.c = fixture()
        self.c["emission_cap_kg"] = 6000
        self.assertFalse(Network(self.c).evaluate((2,))["feasible"])

    def test_risk_weight_endpoints_and_midpoint(self):
        for weight in (0, 0.5, 1):
            c = fixture()
            c["risk_weight"] = weight
            r = Network(c).evaluate((2,))
            self.assertAlmostEqual(r["expected_cost_cny"], 213.24 * 102.1)
            self.assertAlmostEqual(r["objective_cny"], 213.24 * ((1 - weight) * 102.1 + weight * 150))

    def test_speed_and_rate_scenarios(self):
        self.c["scenarios"][0].update(speed_multiplier=0.5, rate_multiplier=2)
        r = Network(self.c).evaluate((2,))["scenarios"][0]
        self.assertEqual(r["arrival_hours"], 20)
        self.assertAlmostEqual(r["transport_cost_cny"], 42080)


class NetworkTests(unittest.TestCase):
    def test_validation(self):
        edits = [lambda c: c["nodes"].append("Origin"),
                 lambda c: c["modes"]["road"].update(speed_kmh=0),
                 lambda c: c["edges"][0].update(distance_km=-1),
                 lambda c: c["edges"][0].update(distance_km=float("nan")),
                 lambda c: c["edges"][0].update(distance_km=True),
                 lambda c: c["edges"].append(deepcopy(c["edges"][0])),
                 lambda c: c["scenarios"][0].update(probability=0.9),
                 lambda c: c.update(risk_weight=1.1),
                 lambda c: c.update(time_window_hours=[20, 10]),
                 lambda c: c["carbon_brackets"][1].update(lower_bound_kg=0)]
        for edit in edits:
            c = fixture()
            edit(c)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                Network(c)

    def test_decoder_backtracks_dead_end_and_prevents_cycles(self):
        n = Network(fixture())
        rng = random.Random(42)
        for _ in range(100):
            priorities = [rng.randrange(len(n.edges)) for _ in n.edges]
            priorities[7] = 100
            result = n.evaluate(n.decode(priorities))
            self.assertEqual(len(result["route"]), len(set(result["route"])))
            self.assertNotIn("DeadEnd", result["route"])

    def test_every_enumerated_route_can_be_encoded(self):
        n = Network(fixture())
        for route in n.routes():
            priorities = [0] * len(n.edges)
            for i in route:
                priorities[i] = len(n.edges) - 1
            self.assertEqual(n.decode(priorities), route)

    def test_direction_and_missing_transfer(self):
        c = fixture()
        c["transfers"] = []
        n = Network(c)
        with self.assertRaises(ValueError):
            n.evaluate((0, 1))
        for route in n.routes():
            self.assertEqual(len(set(n.evaluate(route)["modes"])), 1)
        c["origin"], c["destination"] = c["destination"], c["origin"]
        self.assertIsNone(Network(c).decode([0] * len(n.edges)))

    def test_malformed_routes(self):
        n = Network(fixture())
        for route in ((), (1,), (0,), (2, 2), (0, 5, 6, 1), (-1,), (True,)):
            with self.subTest(route=route), self.assertRaises(ValueError):
                n.evaluate(route)

    def test_decoder_validation_and_expansion_limit(self):
        n = Network(fixture())
        for p in ([], [float("nan")] * len(n.edges)):
            with self.assertRaises(ValueError):
                n.decode(p)
        with self.assertRaises(RuntimeError):
            solve_exact(n, max_states=1)

    def test_exact_synthetic_optimum(self):
        r = solve_exact(Network(fixture()))
        self.assertEqual(r["status"], "optimal")
        self.assertEqual(r["solution"]["edge_indices"], [0, 5, 8])
        # 1,200 km water: (0.045 + 0.012 * 0.05) * 1,200 * 102.1 tonnes.
        self.assertAlmostEqual(r["solution"]["objective_cny"], 5586.912)

    def test_exact_matches_independent_permutation_enumeration(self):
        # Build routes independently of the DFS and compare minimum evaluated costs.
        n = Network(fixture())
        intermediates = [x for x in n.nodes if x not in (n.origin, n.destination)]
        candidates = []
        for length in range(len(intermediates) + 1):
            for middle in itertools.permutations(intermediates, length):
                nodes = (n.origin,) + middle + (n.destination,)
                legs = [[i for i, e in enumerate(n.edges) if e["from"] == a and e["to"] == b] for a, b in zip(nodes, nodes[1:])]
                for route in itertools.product(*legs):
                    r = n.evaluate(route)
                    if r["feasible"]:
                        candidates.append(r["objective_cny"])
        self.assertAlmostEqual(solve_exact(n)["solution"]["objective_cny"], min(candidates))

    def test_exact_infeasibility_and_size_guard(self):
        c = fixture()
        c["emission_cap_kg"] = 0
        self.assertEqual(solve_exact(Network(c))["status"], "infeasible")
        c["nodes"] += ["Unused1", "Unused2", "Unused3", "Unused4"]
        with self.assertRaises(ValueError):
            solve_exact(Network(c))


if __name__ == "__main__":
    unittest.main()
