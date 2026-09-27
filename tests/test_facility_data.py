"""Facility-level evidence registry tests."""

from copy import deepcopy
import csv
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from routing.facility_data import load_registry, registry_summary, validate_registry
from routing.facility_network import available_facility_cases, facility_case_config
from routing.model import Network, solve_exact


ROOT = Path(__file__).resolve().parents[1]


class FacilityRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def test_registry_is_valid_and_facility_level(self):
        summary = registry_summary(self.registry)
        self.assertEqual(summary["facilities"], 20)
        self.assertEqual(summary["service_evidence_records"], 12)
        self.assertGreaterEqual(summary["exact_facilities"], 10)
        self.assertEqual(summary["optimizer_eligible_services"], 0)
        self.assertEqual(summary["calibrated_model_edges"], 7)
        self.assertEqual(summary["runnable_model_cases"], 3)

    def test_plans_and_incomplete_services_are_not_promoted(self):
        services = self.registry["services"]["services"]
        for row in services:
            if row["optimizer_eligible"]:
                self.assertIsNotNone(row["from_facility_id"])
                self.assertIsNotNone(row["to_facility_id"])
                self.assertIsNotNone(row["service_hours"])
                self.assertIsNotNone(row["distance_km"])
        express = next(row for row in services if row["id"] == "cq-sh-express-corridor-2022")
        self.assertFalse(express["optimizer_eligible"])
        self.assertIn("intermediate ports are not called", express["notes"])

    def test_current_facility_is_not_backdated(self):
        facilities = {row["id"]: row for row in self.registry["facilities"]["facilities"]}
        tonghai = facilities["js-nantong-tonghai-terminal"]
        self.assertEqual(tonghai["snapshot_status"]["historical_2022"], "not_applicable")
        self.assertEqual(tonghai["snapshot_status"]["current_reference"], "operational")

    def test_cargo_specific_hub_is_not_default_container_core(self):
        facilities = {row["id"]: row for row in self.registry["facilities"]["facilities"]}
        self.assertEqual(facilities["ah-wuhu-yuxikou-port"]["decision"], "cargo_specific")
        self.assertNotIn("container", facilities["ah-wuhu-yuxikou-port"]["cargo_types"])

    def test_validator_rejects_unresolved_core_and_fake_optimizer_edge(self):
        broken = deepcopy(self.registry)
        unresolved = next(row for row in broken["facilities"]["facilities"]
                          if row["resolution"] != "exact_facility")
        unresolved["decision"] = "core"
        with self.assertRaises(ValueError):
            validate_registry(broken)
        broken = deepcopy(self.registry)
        broken["services"]["services"][0]["optimizer_eligible"] = True
        with self.assertRaises(ValueError):
            validate_registry(broken)

    def test_checked_in_inventory_outputs_match_registry(self):
        output = ROOT / "benchmarks" / "facility-network"
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary, registry_summary(self.registry))
        with (output / "facilities.csv").open(encoding="utf-8") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), summary["facilities"])
        with (output / "services.csv").open(encoding="utf-8") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), summary["service_evidence_records"])
        self.assertTrue(ET.parse(output / "facility-network.svg").getroot().tag.endswith("svg"))

    def test_calibrated_layer_does_not_promote_raw_service_records(self):
        self.assertEqual(len(available_facility_cases()), 3)
        self.assertEqual(sum(row["optimizer_eligible"]
                             for row in self.registry["services"]["services"]), 0)
        model = self.registry["model_inputs"]
        rail = next(row for row in model["edges"]
                    if row["id"] == "cq-guoyuan-luchaogang-rail-calibrated")
        self.assertEqual(rail["distance_km"], 1733)
        self.assertEqual(rail["field_provenance"]["distance_km"]["evidence_class"],
                         "team_collected_model_input")
        self.assertEqual(rail["field_provenance"]["service_hours"]["evidence_class"],
                         "corridor_specific_historical_operation")

    def test_facility_specific_transfer_and_true_multileg_route(self):
        network = Network(facility_case_config(deadline_hours=153))
        solved = solve_exact(network)["solution"]
        self.assertEqual(solved["modes"], ["rail", "road"])
        self.assertEqual(solved["route"], ["cq-guoyuan-port", "sh-luchaogang-rail",
                                           "sh-yangshan-port"])
        scenario = solved["scenarios"][0]
        self.assertAlmostEqual(scenario["arrival_hours"], 64.75)
        self.assertEqual(scenario["transfer_cost_cny"], 30)
        self.assertIsNone(network.transfer_at("cq-guoyuan-port", "rail", "road"))
        self.assertIsNotNone(network.transfer_at("sh-luchaogang-rail", "rail", "road"))

    def test_operator_and_spot_inputs_replace_prior_numeric_assumptions(self):
        edges = {row["id"]: row for row in self.registry["model_inputs"]["edges"]}
        rail = edges["cq-guoyuan-luchaogang-rail-calibrated"]
        drayage = edges["luchaogang-yangshan-road-drayage-calibrated"]
        express = edges["cq-guoyuan-yangshan-water-express-calibrated"]
        regular = edges["cq-guoyuan-yangshan-water-regular-calibrated"]
        self.assertEqual(rail["service_hours"], {"optimistic": 55, "central": 57.5,
                                                  "conservative": 60})
        self.assertEqual(drayage["distance_km"], 45)
        self.assertEqual(drayage["quoted_cost_cny_per_20ft"], 200)
        self.assertEqual(drayage["field_provenance"]["quoted_cost_cny_per_20ft"]
                         ["evidence_class"], "marketplace_observation")
        self.assertEqual(express["quoted_cost_cny_per_20ft"], 1400)
        self.assertEqual(regular["quoted_cost_cny_per_20ft"], 1130)
        self.assertEqual(regular["service_hours"]["central"], 240)
        self.assertEqual(drayage["handling_hours"], 1)
        self.assertEqual(drayage["field_provenance"]["handling_hours"]
                         ["evidence_class"], "official_reported")

    def test_operational_gap_audit_preserves_unknowns(self):
        audit = json.loads((ROOT / "data" / "operational_evidence_gaps.json")
                           .read_text(encoding="utf-8"))
        rows = {row["id"]: row for row in audit["gaps"]}
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows["rail-current-service"]["status"], "partially_filled")
        self.assertIn("route_specific_cancellation_rate", rows["rail-current-service"]
                      ["remaining_unknowns"])
        self.assertEqual(rows["rail-quote-scope"]["status"], "unresolved")
        self.assertEqual(rows["emissions-equipment-load"]["status"], "partially_filled")

    def test_deadline_and_carbon_price_change_facility_route(self):
        def best(deadline, price=0):
            network = Network(facility_case_config(
                deadline_hours=deadline, carbon_price_cny_per_tonne=price))
            return solve_exact(network)["solution"]

        self.assertIsNone(best(60))
        self.assertEqual(best(66)["modes"], ["rail", "road"])
        self.assertEqual(best(96)["modes"], ["rail", "road"])
        self.assertEqual(best(204)["edge_indices"], [3])
        self.assertEqual(best(240)["edge_indices"], [4])
        self.assertEqual(best(240, 7000)["modes"], ["rail", "road"])

    def test_facility_analysis_outputs_are_complete_and_visualized(self):
        output = ROOT / "benchmarks" / "facility-case-analysis"
        report = json.loads((output / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(report["grid"]["rows"], 1260)
        self.assertGreater(report["switch_boundaries_central_15t"]
                           ["rail_beats_express_water_above_cny_per_tco2"], 5000)
        with (output / "scenario-grid.csv").open(encoding="utf-8") as stream:
            self.assertEqual(sum(1 for _ in csv.DictReader(stream)), 1260)
        with (output / "route-options.csv").open(encoding="utf-8") as stream:
            self.assertEqual(sum(1 for _ in csv.DictReader(stream)), 4)
        for name in ("deadline-carbon-phase.svg", "cost-emissions-frontier.svg",
                     "route-components.svg", "route-road-direct.svg",
                     "route-rail-road-via-luchaogang.svg",
                     "route-water-express-bundled.svg",
                     "route-water-regular-bundled.svg"):
            self.assertTrue(ET.parse(output / name).getroot().tag.endswith("svg"))


if __name__ == "__main__":
    unittest.main()
