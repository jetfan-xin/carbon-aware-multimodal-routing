"""Evidence-calibrated corridor configurations.

Operator-reported lane comparisons, official market indices and service times
remain tagged with source identifiers. Distances, payloads, endpoint mappings
and linear edge allocation assumptions are separately tagged and must not be
described as observed freight records.
"""

from copy import deepcopy
import json
from pathlib import Path

from .synthetic import generate_network


ROOT = Path(__file__).resolve().parents[1]


def load_benchmarks(path=None):
    location = Path(path) if path else ROOT / "data" / "real_world_benchmarks.json"
    return json.loads(location.read_text(encoding="utf-8"))


def carbon_schedule(price_cny_per_tonne):
    return [{"lower_bound_kg": 0, "rate_cny_per_kg": price_cny_per_tonne / 1000}]


def historical_progressive_schedule():
    return [
        {"lower_bound_kg": 0, "rate_cny_per_kg": 0.05},
        {"lower_bound_kg": 150000, "rate_cny_per_kg": 0.10},
        {"lower_bound_kg": 500000, "rate_cny_per_kg": 0.15},
        {"lower_bound_kg": 1000000, "rate_cny_per_kg": 0.20},
    ]


def direct_corridor_config(corridor_id="chongqing-shanghai", payload_tonnes=15,
                           deadline_hours=240, carbon_price_cny_per_tonne=0,
                           hard_deadline=True, time_case="p50"):
    data = load_benchmarks()
    corridor = next(row for row in data["corridors"] if row["id"] == corridor_id)
    if time_case not in {"p10", "p50", "p90"}:
        raise ValueError("time_case must be p10, p50 or p90")
    modes = {}
    edges = []
    for route in corridor["route_options"]:
        if route.get("quoted_cost_cny_per_20ft") is None or route.get("distance_km") is None:
            continue
        mode = route["mode"]
        modes.setdefault(mode, {
            "speed_kmh": route["distance_km"] / route["service_hours"]["p50"],
            "rate_cny_per_tonne_km": 0,
            "emissions_kg_per_tonne_km": data["emission_factors_kg_per_tonne_km"][mode]["value"],
        })
        edges.append({
            "id": route["id"], "from": corridor["origin"], "to": corridor["destination"],
            "mode": mode, "distance_km": route["distance_km"],
            "quoted_cost_cny_per_unit": route["quoted_cost_cny_per_20ft"],
            "quoted_cost_unit": "shipment", "cost_scope": route["cost_scope"],
            "service_hours": route["service_hours"][time_case],
            "source_ids": route["source_ids"], "evidence_class": route["evidence_class"],
            "available": True,
        })
    return {
        "schema_version": 3, "description": corridor["description"],
        "data_classification": "evidence_calibrated",
        "nodes": [corridor["origin"], corridor["destination"]],
        "coordinates": corridor["coordinates"], "origin": corridor["origin"],
        "destination": corridor["destination"], "modes": modes, "transfers": [],
        "edges": edges, "time_window_hours": [0, deadline_hours],
        "storage_cny_per_tonne_hour": 0, "late_penalty_cny_per_tonne_hour": 30,
        "hard_deadline": hard_deadline, "emission_cap_kg": None, "risk_weight": 0,
        "carbon_brackets": carbon_schedule(carbon_price_cny_per_tonne),
        "scenarios": [{"name": f"one-20ft-{payload_tonnes:g}t", "tonnes": payload_tonnes,
                       "shipment_units": 1, "probability": 1,
                       "speed_multiplier": 1, "service_time_multiplier": 1,
                       "rate_multiplier": 1}],
    }


def calibrated_23city_config(deadline_hours=240, payload_tonnes=15,
                             carbon_price_cny_per_tonne=0, seed=42):
    """Synthetic topology with observed end-to-end lane values allocated by distance."""
    benchmark = load_benchmarks()
    corridor = next(row for row in benchmark["corridors"] if row["id"] == "chongqing-shanghai")
    by_mode = {row["mode"]: row for row in corridor["route_options"] if row["id"] in
               {"cq-sh-road", "cq-sh-rail", "cq-sh-water-regular"}}
    config = generate_network(node_count=23, density=1, seed=seed)
    config["schema_version"] = 3
    config["data_classification"] = "synthetic_topology_evidence_calibrated_parameters"
    config["description"] = "Synthetic 23-city topology; official corridor quotes/times linearly allocated over model edges."
    for mode, values in config["modes"].items():
        values["emissions_kg_per_tonne_km"] = benchmark["emission_factors_kg_per_tonne_km"][mode]["value"]
    for edge in config["edges"]:
        lane = by_mode[edge["mode"]]
        fraction = edge["distance_km"] / lane["distance_km"]
        edge["quoted_cost_cny_per_unit"] = lane["quoted_cost_cny_per_20ft"] * fraction
        edge["quoted_cost_unit"] = "shipment"
        edge["service_hours"] = lane["service_hours"]["p50"] * fraction
        edge["calibration_method"] = "linear allocation of end-to-end benchmark; model assumption"
        edge["source_ids"] = lane["source_ids"]
    config["time_window_hours"] = [0, deadline_hours]
    config["hard_deadline"] = True
    config["carbon_brackets"] = carbon_schedule(carbon_price_cny_per_tonne)
    config["scenarios"] = [{"name": "one-20ft-calibration", "tonnes": payload_tonnes,
                            "shipment_units": 1, "probability": 1,
                            "speed_multiplier": 1, "service_time_multiplier": 1,
                            "rate_multiplier": 1}]
    return config
