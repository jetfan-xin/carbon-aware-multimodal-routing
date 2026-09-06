"""Audit archived arithmetic without pretending to rerun the 2022 optimizer.

Standard library only. All operations are offline and read-only.
"""

import argparse
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENT = Decimal("0.01")


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Expected a finite number")
    return result


def percentage_change(new, baseline):
    baseline = number(baseline)
    if baseline <= 0:
        raise ValueError("A comparison baseline must be positive")
    return (number(new) - baseline) / baseline * 100


def component_cost(case):
    total = sum(number(case[k]) for k in ("transport_cny", "transfer_cny", "time_cny"))
    if case["carbon_in_objective"]:
        total += number(case["carbon_cny"])
    return total


def audit_case(case, deadline):
    monetary_fields = ("reported_total_cny", "transport_cny", "transfer_cny", "time_cny", "carbon_cny")
    for field in (*monetary_fields, "hours", "emissions_kg", "transport_emissions_kg", "transfer_emissions_kg"):
        if number(case[field]) < 0:
            raise ValueError("Negative archived quantity: " + field)
    route, modes = case.get("route"), case.get("modes")
    if route is not None and (modes is None or len(modes) != len(route) - 1):
        raise ValueError("A route needs one transport mode per leg")
    cost_delta = number(case["reported_total_cny"]) - component_cost(case)
    emission_delta = number(case["emissions_kg"]) - number(case["transport_emissions_kg"]) - number(case["transfer_emissions_kg"])
    return {
        "id": case["id"],
        "cost_component_sum_cny": str(component_cost(case)),
        "reported_minus_component_cost_cny": str(cost_delta),
        "cost_within_one_cent": abs(cost_delta) <= CENT,
        "reported_minus_component_emissions_kg": str(emission_delta),
        "emissions_within_0_01_kg": abs(emission_delta) <= CENT,
        "lateness_hours": str(max(Decimal(0), number(case["hours"]) - number(deadline))),
    }


def audit_document(document):
    cases = document["cases"]
    lookup = {case["id"]: case for case in cases}
    if len(lookup) != len(cases):
        raise ValueError("Duplicate case identifiers")
    deadline = number(document["deadline_hours"])
    if deadline < 0:
        raise ValueError("Deadline must be nonnegative")
    combined = lookup["combined"]
    constrained = lookup["emission_constrained"]
    baseline = lookup["reference_multimodal"]
    return {
        "purpose": "Arithmetic audit of historical reported outputs, not a solver reproduction",
        "cases": [audit_case(case, deadline) for case in cases],
        "comparisons": {
            "emission_constrained_vs_combined": {
                "cost_change_percent": str(percentage_change(constrained["reported_total_cny"], combined["reported_total_cny"]).quantize(CENT)),
                "emissions_change_percent": str(percentage_change(constrained["emissions_kg"], combined["emissions_kg"]).quantize(CENT)),
            },
            "combined_vs_reference_multimodal": {
                "cost_change_percent": str(percentage_change(combined["reported_total_cny"], baseline["reported_total_cny"]).quantize(CENT)),
                "emissions_change_percent": str(percentage_change(combined["emissions_kg"], baseline["emissions_kg"]).quantize(CENT)),
                "caveat": "Baseline generation was not recovered; this comparison is not a validated performance benchmark.",
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "case_study.json")
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as stream:
        result = audit_document(json.load(stream))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
