"""Runnable facility-level cases built from separately classified inputs.

The raw service registry answers whether a service or facility is documented.
This module builds analysis cases only from ``model_inputs.json``, where each
numeric field states whether it is reported, team-collected, derived or an
explicit assumption.
"""

from __future__ import annotations

from copy import deepcopy

from .facility_data import load_registry, validate_registry
from .real_world import carbon_schedule


TIME_CASES = {"optimistic", "central", "conservative"}


def available_facility_cases(data_dir=None):
    registry = load_registry() if data_dir is None else load_registry(data_dir)
    validate_registry(registry)
    return [row["id"] for row in registry["model_inputs"]["cases"]]


def facility_case_config(case_id="cq-guoyuan-to-yangshan-calibrated", *,
                         payload_tonnes=15, deadline_hours=216,
                         carbon_price_cny_per_tonne=0, time_case="central",
                         data_dir=None):
    """Return a standard :class:`routing.model.Network` configuration.

    ``central`` means the middle analysis case, not necessarily a measured
    median.  The provenance record for each edge explains which values are
    reported and which are sensitivity assumptions.
    """
    if time_case not in TIME_CASES:
        raise ValueError("time_case must be optimistic, central or conservative")
    registry = load_registry() if data_dir is None else load_registry(data_dir)
    validate_registry(registry)
    data = registry["model_inputs"]
    cases = {row["id"]: row for row in data["cases"]}
    if case_id not in cases:
        raise ValueError(f"unknown facility case: {case_id}")
    case = cases[case_id]
    by_edge = {row["id"]: row for row in data["edges"]}
    by_transfer = {row["id"]: row for row in data["transfers"]}

    edges = []
    nodes = []
    for edge_id in case["edge_ids"]:
        source = deepcopy(by_edge[edge_id])
        edge = {
            "id": source["id"],
            "from": source["from_facility_id"],
            "to": source["to_facility_id"],
            "mode": source["mode"],
            "distance_km": source["distance_km"],
            "quoted_cost_cny_per_unit": source["quoted_cost_cny_per_20ft"],
            "quoted_cost_unit": "shipment",
            "cost_scope": source["cost_scope"],
            "service_hours": source["service_hours"][time_case],
            "field_provenance": source["field_provenance"],
            "admission_note": source["admission_note"],
            "available": True,
        }
        if "handling_hours" in source:
            edge["handling_hours"] = source["handling_hours"]
        if "scheduled_wait_hours" in source:
            waits = source["scheduled_wait_hours"]
            edge["scheduled_wait_hours"] = waits[time_case] if isinstance(waits, dict) else waits
        edges.append(edge)
        for node in (edge["from"], edge["to"]):
            if node not in nodes:
                nodes.append(node)

    # Stable presentation order with the requested endpoints at the ends.
    nodes = [case["origin"]] + [node for node in nodes
                                if node not in {case["origin"], case["destination"]}] + [case["destination"]]
    transfers = [deepcopy(by_transfer[row_id]) for row_id in case["transfer_ids"]]
    modes = {
        name: {
            "speed_kmh": row["speed_kmh"],
            "rate_cny_per_tonne_km": 0,
            "emissions_kg_per_tonne_km": row["emissions_kg_per_tonne_km"],
            "source_id": row["source_id"],
        }
        for name, row in data["mode_parameters"].items()
        if any(edge["mode"] == name for edge in edges)
    }
    return {
        "schema_version": 3,
        "description": case["route_semantics"],
        "data_classification": case["classification"],
        "model_case_id": case_id,
        "time_case": time_case,
        "nodes": nodes,
        "origin": case["origin"],
        "destination": case["destination"],
        "modes": modes,
        "transfers": transfers,
        "edges": edges,
        "time_window_hours": [0, deadline_hours],
        "storage_cny_per_tonne_hour": 0,
        "late_penalty_cny_per_tonne_hour": 30,
        "hard_deadline": True,
        "emission_cap_kg": None,
        "risk_weight": 0,
        "carbon_brackets": carbon_schedule(carbon_price_cny_per_tonne),
        "scenarios": [{
            "name": f"one-20ft-{payload_tonnes:g}t",
            "tonnes": payload_tonnes,
            "shipment_units": 1,
            "probability": 1,
            "speed_multiplier": 1,
            "service_time_multiplier": 1,
            "rate_multiplier": 1,
        }],
    }
