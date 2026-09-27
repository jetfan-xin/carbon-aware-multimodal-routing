"""Portfolio-level accounting for aggregate progressive carbon charges.

The route evaluator prices one scenario. This module deliberately removes its
per-route carbon charge and reapplies the schedule once to portfolio emissions,
so carbon brackets are not reset for every order or consolidated batch.
"""

from itertools import combinations
import math

from .model import carbon_cost


def aggregate_portfolio(evaluations, brackets):
    if not evaluations:
        raise ValueError("at least one route evaluation is required")
    rows = []
    for result in evaluations:
        if len(result["scenarios"]) != 1 or result["scenarios"][0]["probability"] != 1:
            raise ValueError("portfolio aggregation requires one deterministic scenario per evaluation")
        rows.append(result["scenarios"][0])
    transport = math.fsum(row["transport_cost_cny"] for row in rows)
    transfer = math.fsum(row["transfer_cost_cny"] for row in rows)
    time_cost = math.fsum(row["time_cost_cny"] for row in rows)
    emissions = math.fsum(row["emissions_kg"] for row in rows)
    carbon = carbon_cost(emissions, brackets)
    return {
        "shipments": len(rows), "transport_cost_cny": transport,
        "transfer_cost_cny": transfer, "time_cost_cny": time_cost,
        "emissions_kg": emissions, "carbon_cost_cny": carbon,
        "total_cost_cny": transport + transfer + time_cost + carbon,
        "all_feasible": all(result["feasible"] for result in evaluations),
    }


def _compositions(total, parts):
    """Yield nonnegative integer tuples of length parts summing to total."""
    if parts == 1:
        yield (total,)
        return
    for cuts in combinations(range(total + parts - 1), parts - 1):
        points = (-1,) + cuts + (total + parts - 1,)
        yield tuple(points[i + 1] - points[i] - 1 for i in range(parts))


def optimize_homogeneous_portfolio(route_results, shipment_count, brackets):
    """Exact allocation among up to four route options for identical shipments."""
    if not isinstance(shipment_count, int) or isinstance(shipment_count, bool) or shipment_count < 1:
        raise ValueError("shipment_count must be a positive integer")
    feasible = [row for row in route_results if row["feasible"]]
    if not feasible:
        return {"status": "infeasible", "solution": None}
    if len(feasible) > 4:
        raise ValueError("exact portfolio allocator is limited to four feasible route options")
    options = []
    for result in feasible:
        row = result["scenarios"][0]
        options.append({
            "route": result["route"], "modes": result["modes"],
            "noncarbon_cost_cny": row["total_cost_cny"] - row["carbon_cost_cny"],
            "emissions_kg": row["emissions_kg"], "arrival_hours": row["arrival_hours"],
        })
    best = None
    for counts in _compositions(shipment_count, len(options)):
        emissions = math.fsum(count * option["emissions_kg"] for count, option in zip(counts, options))
        noncarbon = math.fsum(count * option["noncarbon_cost_cny"] for count, option in zip(counts, options))
        carbon = carbon_cost(emissions, brackets)
        candidate = {
            "counts": list(counts), "total_cost_cny": noncarbon + carbon,
            "noncarbon_cost_cny": noncarbon, "carbon_cost_cny": carbon,
            "emissions_kg": emissions,
        }
        if best is None or candidate["total_cost_cny"] < best["total_cost_cny"]:
            best = candidate
    best["options"] = options
    return {"status": "optimal-enumeration", "solution": best}
