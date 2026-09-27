"""Real Geatpy integration suite; mandatory in the container and Linux CI job."""

import importlib.util
import os
import unittest

from routing.model import Network, solve_exact
from test_routing import fixture

AVAILABLE = importlib.util.find_spec("geatpy") is not None
if os.environ.get("REQUIRE_GEATPY") == "1" and not AVAILABLE:
    raise RuntimeError("The integration job requires a real Geatpy installation")


@unittest.skipUnless(AVAILABLE, "Geatpy is optional outside the integration environment")
class GeatpyTests(unittest.TestCase):
    def solve(self, config=None, **kwargs):
        from routing.geatpy_solver import solve_geatpy
        return solve_geatpy(Network(config or fixture()), **kwargs)

    def test_matches_exact_across_seeds(self):
        expected = solve_exact(Network(fixture()))["solution"]["objective_cny"]
        for seed in (0, 7, 42):
            for adaptive in (False, True):
                with self.subTest(seed=seed, adaptive=adaptive):
                    r = self.solve(seed=seed, population=40, generations=30, adaptive=adaptive)
                    self.assertAlmostEqual(r["solution"]["objective_cny"], expected)
                    self.assertTrue(r["solution"]["feasible"])

    def test_restart_and_seed_reproducibility(self):
        a = self.solve(population=12, generations=12, patience=2)
        b = self.solve(population=12, generations=12, patience=2)
        self.assertEqual(a, b)
        self.assertGreater(a["restarts"], 0)
        self.assertGreater(a["route_evaluations"], 12 * 12)
        self.assertEqual(len(a["trace"]), 12)
        best = [x["best_objective_cny"] for x in a["trace"]]
        self.assertEqual(best, sorted(best, reverse=True))

    def test_baseline_has_no_restarts(self):
        r = self.solve(population=12, generations=12, patience=2, adaptive=False, catastrophe=False)
        self.assertEqual(r["restarts"], 0)
        self.assertEqual(r["route_evaluations"], 144)

    def test_ablation_flags_are_independent(self):
        adaptive = self.solve(population=12, generations=8, patience=1,
                              adaptive=True, catastrophe=False)
        catastrophe = self.solve(population=12, generations=8, patience=1,
                                 adaptive=False, catastrophe=True)
        self.assertEqual(adaptive["solver"], "geatpy-sega-adaptive-only")
        self.assertEqual(adaptive["restarts"], 0)
        self.assertEqual(catastrophe["solver"], "geatpy-sega-catastrophe-only")

    def test_infeasible_is_not_reported_as_a_solution(self):
        c = fixture()
        c["emission_cap_kg"] = 0
        r = self.solve(c, population=8, generations=5, patience=2)
        self.assertIsNone(r["solution"])
        self.assertEqual(r["status"], "no-feasible-route-found")

    def test_hard_deadline_matches_exact(self):
        c = fixture()
        c.update(time_window_hours=[0, 15], hard_deadline=True)
        r = self.solve(c, population=40, generations=25)
        self.assertAlmostEqual(r["solution"]["objective_cny"], solve_exact(Network(c))["solution"]["objective_cny"])

    def test_problem_array_shapes(self):
        import geatpy as ea
        import numpy as np
        from routing.geatpy_solver import FreightProblem
        problem = FreightProblem(Network(fixture()))
        pop = ea.Population(Encoding="RI", Field=(problem.varTypes, problem.ranges, problem.borders), NIND=2)
        pop.initChrom()
        pop.Phen = pop.decoding()
        problem.aimFunc(pop)
        self.assertEqual(pop.ObjV.shape, (2, 1))
        self.assertEqual(pop.CV.shape, (2, 1))
        self.assertTrue(np.all(np.isfinite(pop.ObjV)))

    def test_deadline_makes_multimodal_route_optimal(self):
        c = fixture()
        c.update(time_window_hours=[0, 35], hard_deadline=True)
        exact = solve_exact(Network(c))["solution"]
        self.assertEqual(exact["edge_indices"], [0, 1])
        r = self.solve(c, population=40, generations=30)
        self.assertEqual(r["solution"]["modes"], ["water", "rail"])
        self.assertAlmostEqual(r["solution"]["objective_cny"], exact["objective_cny"])

    def test_single_edge_network(self):
        c = fixture()
        c["edges"] = [c["edges"][2]]
        r = self.solve(c, population=8, generations=5)
        self.assertEqual(r["solution"]["modes"], ["road"])

    def test_graph_heuristic_seed_is_inserted(self):
        from routing.model import solve_state_dijkstra
        network = Network(fixture())
        expected = solve_state_dijkstra(network)["solution"]["objective_cny"]
        result = self.solve(population=8, generations=1, heuristic_seed=True)
        self.assertEqual(result["solver"], "geatpy-sega-hybrid")
        self.assertAlmostEqual(result["solution"]["objective_cny"], expected)

    def test_disconnected_network(self):
        c = fixture()
        c["origin"], c["destination"] = c["destination"], c["origin"]
        r = self.solve(c, population=8, generations=5, patience=2)
        self.assertIsNone(r["solution"])

    def test_invalid_search_budget(self):
        for args in (dict(population=1), dict(generations=0), dict(seed=-1), dict(patience=0)):
            with self.assertRaises(ValueError):
                self.solve(**args)


if __name__ == "__main__":
    unittest.main()
