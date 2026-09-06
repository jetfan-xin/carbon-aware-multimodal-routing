"""Offline checks for the archive-auditing utility."""

import copy
import importlib.util
import json
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit_results", ROOT / "tools" / "audit_results.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ResultAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((ROOT / "data" / "case_study.json").read_text())
        cls.cases = {case["id"]: case for case in cls.document["cases"]}
        cls.result = audit.audit_document(cls.document)

    def test_seven_archived_cases(self):
        self.assertEqual(len(self.cases), 7)

    def test_economic_objective_excludes_carbon(self):
        self.assertEqual(audit.component_cost(self.cases["economic"]), Decimal("10118.65"))

    def test_combined_objective_includes_carbon(self):
        self.assertEqual(audit.component_cost(self.cases["combined"]), Decimal("10272.70"))

    def test_rounding_difference_is_retained(self):
        check = audit.audit_case(self.cases["combined"], 62)
        self.assertEqual(Decimal(check["reported_minus_component_cost_cny"]), Decimal("-0.01"))

    def test_cost_tradeoff(self):
        self.assertEqual(self.result["comparisons"]["emission_constrained_vs_combined"]["cost_change_percent"], "10.56")

    def test_emissions_tradeoff(self):
        self.assertEqual(self.result["comparisons"]["emission_constrained_vs_combined"]["emissions_change_percent"], "-20.06")

    def test_late_arrival_is_not_hidden(self):
        check = audit.audit_case(self.cases["emission_constrained"], 62)
        self.assertEqual(Decimal(check["lateness_hours"]), Decimal("1.50"))

    def test_baseline_emission_mismatch_is_detected(self):
        check = audit.audit_case(self.cases["reference_multimodal"], 62)
        self.assertFalse(check["emissions_within_0_01_kg"])
        self.assertEqual(Decimal(check["reported_minus_component_emissions_kg"]), Decimal("5.85"))

    def test_zero_baseline_rejected(self):
        with self.assertRaises(ValueError):
            audit.percentage_change(10, 0)

    def test_nonfinite_number_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(ValueError):
                audit.number(value)

    def test_duplicate_case_rejected(self):
        doc = copy.deepcopy(self.document)
        doc["cases"].append(doc["cases"][0])
        with self.assertRaises(ValueError):
            audit.audit_document(doc)

    def test_invalid_route_rejected(self):
        case = copy.deepcopy(self.cases["combined"])
        case["modes"] = ["water"]
        with self.assertRaises(ValueError):
            audit.audit_case(case, 62)

    def test_negative_value_rejected(self):
        case = copy.deepcopy(self.cases["combined"])
        case["hours"] = "-1"
        with self.assertRaises(ValueError):
            audit.audit_case(case, 62)

    def test_scenario_probabilities_and_expected_load(self):
        params = json.loads((ROOT / "data" / "parameter_snapshot.json").read_text())
        scenarios = params["demand_scenarios"]
        self.assertEqual(sum(audit.number(s["probability"]) for s in scenarios), Decimal(1))
        mean = sum(audit.number(s["tonnes"]) * audit.number(s["probability"]) for s in scenarios)
        self.assertEqual(mean, Decimal("102.1"))


if __name__ == "__main__":
    unittest.main()
