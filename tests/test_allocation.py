"""Regression tests for globally coupled order allocation."""

import unittest

from routing.allocation import (evaluate_assignment, generate_candidate_pools,
                                solve_exact_allocation, solve_greedy_allocation,
                                solve_opportunity_greedy_allocation)
from routing.allocation_ga import solve_allocation_ga


def tiny_config():
    return {
        "schema_version": 3,
        "nodes": ["Origin", "Hub", "Destination"],
        "origin": "Origin",
        "destination": "Destination",
        "modes": {
            "rail": {"speed_kmh": 50, "rate_cny_per_tonne_km": 0,
                     "emissions_kg_per_tonne_km": 0.01},
            "road": {"speed_kmh": 50, "rate_cny_per_tonne_km": 0,
                     "emissions_kg_per_tonne_km": 0.10},
        },
        "transfers": [],
        "edges": [
            {"id": "rail-direct", "from": "Origin", "to": "Destination",
             "mode": "rail", "distance_km": 100,
             "quoted_cost_cny_per_unit": 100, "quoted_cost_unit": "shipment",
             "service_hours": 5,
             "available": True},
            {"id": "road-direct", "from": "Origin", "to": "Destination",
             "mode": "road", "distance_km": 100,
             "quoted_cost_cny_per_unit": 180, "quoted_cost_unit": "shipment",
             "service_hours": 4,
             "available": True},
        ],
        "time_window_hours": [0, 24],
        "storage_cny_per_tonne_hour": 0,
        "late_penalty_cny_per_tonne_hour": 30,
        "hard_deadline": True,
        "emission_cap_kg": None,
        "risk_weight": 0,
        "carbon_brackets": [
            {"lower_bound_kg": 0, "rate_cny_per_kg": 1},
            {"lower_bound_kg": 50, "rate_cny_per_kg": 2},
        ],
        "scenarios": [{"name": "placeholder", "tonnes": 1, "probability": 1,
                       "speed_multiplier": 1, "rate_multiplier": 1}],
    }


def tiny_orders():
    return [
        {"order_id": "A", "origin": "Origin", "destination": "Destination",
         "tonnes": 6, "deadline_hours": 12, "shipment_units": 1},
        {"order_id": "B", "origin": "Origin", "destination": "Destination",
         "tonnes": 6, "deadline_hours": 12, "shipment_units": 1},
    ]


def tiny_departures():
    return [{"departure_id": "R0", "edge_id": "rail-direct", "departure_hour": 0,
             "capacity_tonnes": 6, "capacity_units": 1,
             "evidence_class": "test_fixture"}]


class CandidateGenerationTests(unittest.TestCase):
    def setUp(self):
        self.generated = generate_candidate_pools(
            tiny_config(), tiny_orders(), tiny_departures(), top_k=4)

    def test_route_departure_candidates_are_generated(self):
        pools = self.generated["candidate_pools"]
        self.assertEqual(set(pools), {"A", "B"})
        for order_id in ("A", "B"):
            self.assertEqual(len(pools[order_id]), 2)
            rail = next(row for row in pools[order_id] if row["modes"] == ["rail"])
            road = next(row for row in pools[order_id] if row["modes"] == ["road"])
            self.assertEqual(rail["departure_ids"], ["R0"])
            self.assertEqual(rail["arrival_hour"], 5)
            self.assertEqual(road["departure_ids"], [])

    def test_shared_departure_capacity_is_global(self):
        pools = self.generated["candidate_pools"]
        rail_gene = [next(i for i, row in enumerate(pools[order_id])
                          if row["modes"] == ["rail"]) for order_id in ("A", "B")]
        result = evaluate_assignment(self.generated["orders"], pools,
                                     self.generated["departures"], rail_gene,
                                     tiny_config()["carbon_brackets"])
        self.assertFalse(result["feasible"])
        self.assertAlmostEqual(result["capacity_violation"], 2)

    def test_capacity_only_resource_does_not_change_arrival(self):
        resources = [{"departure_id": "RAIL-HORIZON", "edge_id": "rail-direct",
                      "capacity_only": True, "capacity_tonnes": 6,
                      "capacity_units": 1}]
        generated = generate_candidate_pools(
            tiny_config(), tiny_orders(), resources, top_k=4)
        rail = next(row for row in generated["candidate_pools"]["A"]
                    if row["modes"] == ["rail"])
        self.assertEqual(rail["arrival_hour"], 5)
        self.assertEqual(rail["departure_ids"], [])
        self.assertEqual(rail["capacity_claims"][0]["departure_id"], "RAIL-HORIZON")


class AllocationSolverTests(unittest.TestCase):
    def setUp(self):
        self.generated = generate_candidate_pools(
            tiny_config(), tiny_orders(), tiny_departures(), top_k=4)
        self.args = (self.generated["orders"], self.generated["candidate_pools"],
                     self.generated["departures"], tiny_config()["carbon_brackets"])

    def test_exact_allocation_splits_shared_capacity(self):
        exact = solve_exact_allocation(*self.args)
        self.assertEqual(exact["status"], "optimal")
        self.assertTrue(exact["solution"]["feasible"])
        modes = [row["modes"] for row in exact["solution"]["selected_candidates"]]
        self.assertEqual(sorted(modes), [["rail"], ["road"]])
        self.assertEqual(exact["candidate_evaluations"], 4)

    def test_greedy_and_ga_find_feasible_allocation(self):
        exact = solve_exact_allocation(*self.args)["solution"]
        greedy = solve_greedy_allocation(*self.args)["solution"]
        ga = solve_allocation_ga(*self.args, population=12, generations=8,
                                 seed=7, patience=2, heuristic_seed=True)
        self.assertTrue(greedy["feasible"])
        self.assertEqual(ga["status"], "feasible-heuristic")
        self.assertAlmostEqual(ga["solution"]["total_cost_cny"],
                               exact["total_cost_cny"])
        self.assertEqual(ga["candidate_evaluations"], 96)
        self.assertGreater(ga["heuristic_seed_evaluations"], 0)

    def test_fixed_ga_uses_capacity_feasible_random_initialization(self):
        ga = solve_allocation_ga(*self.args, population=8, generations=2,
                                 seed=3, adaptive=False, catastrophe=False)
        self.assertEqual(ga["status"], "feasible-heuristic")
        self.assertEqual(ga["heuristic_seed_evaluations"], 0)
        self.assertTrue(ga["solution"]["feasible"])

    def test_diversity_controller_bounds_mutated_gene_budget(self):
        ga = solve_allocation_ga(
            *self.args, population=8, generations=4, seed=3, patience=2,
            adaptive=True, catastrophe=False, adaptive_control="diversity-v2",
            mutation_base=1, mutation_cap=2)
        self.assertTrue(all(1 <= row["expected_mutated_genes"] <= 2
                            for row in ga["trace"]))
        self.assertTrue(all(0 <= row["population_diversity"] <= 1
                            for row in ga["trace"]))

    def test_archive_seed_does_not_replace_random_population(self):
        common = dict(population=8, generations=1, seed=5, patience=2,
                      adaptive=True, catastrophe=True,
                      adaptive_control="diversity-v2", restart_fraction=.5)
        unseeded = solve_allocation_ga(*self.args, **common)
        archive = solve_allocation_ga(
            *self.args, **common, heuristic_seed=True,
            heuristic_seed_mode="archive")
        self.assertEqual(
            archive["trace"][0]["population_best_objective_cny"],
            unseeded["trace"][0]["population_best_objective_cny"])
        self.assertLessEqual(archive["solution"]["total_cost_cny"],
                             unseeded["solution"]["total_cost_cny"])

    def test_progressive_carbon_is_applied_once(self):
        exact = solve_exact_allocation(*self.args)["solution"]
        self.assertGreater(exact["carbon_cost_cny"], 0)
        self.assertAlmostEqual(
            exact["total_cost_cny"],
            exact["noncarbon_cost_cny"] + exact["carbon_cost_cny"])

    def test_opportunity_greedy_is_feasible_and_auditable(self):
        result = solve_opportunity_greedy_allocation(*self.args)
        self.assertEqual(result["solver"], "greedy-opportunity-cost")
        self.assertTrue(result["solution"]["feasible"])
        self.assertEqual(result["candidate_evaluations"], 4)


if __name__ == "__main__":
    unittest.main()
