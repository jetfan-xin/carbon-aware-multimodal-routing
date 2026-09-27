"""Candidate generation and globally coupled freight-order allocation.

The single-route model remains useful for evaluating one path.  This module
adds the missing portfolio decision: different orders compete for the same
scheduled departures and the progressive carbon schedule is applied once to
their aggregate emissions.

Candidate routes are generated independently for each order.  That graph step
is intentionally only preprocessing; shared capacity and aggregate carbon are
resolved by the allocation solvers rather than hidden inside the route seed.
"""

from __future__ import annotations

from copy import deepcopy
import heapq
from itertools import product
import math

from .model import Network, carbon_cost


def _number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return float(value)


def _carbon_brackets(brackets):
    """Accept either the public JSON records or Network's tuple form."""
    normalized = []
    for row in brackets:
        if isinstance(row, dict):
            lower = row["lower_bound_kg"]
            rate = row["rate_cny_per_kg"]
        else:
            lower, rate = row
        normalized.append((_number(lower, "carbon lower bound", nonnegative=True),
                           _number(rate, "carbon marginal rate", nonnegative=True)))
    if not normalized or normalized[0][0] != 0:
        raise ValueError("carbon schedule must start at zero")
    if any(current[0] <= previous[0] or current[1] < previous[1]
           for previous, current in zip(normalized, normalized[1:])):
        raise ValueError("carbon bounds must increase and rates must not decrease")
    return normalized


def normalize_allocation_orders(orders, nodes):
    """Validate orders for a common planning horizon.

    ``deadline_hours`` and ``release_hour`` are absolute hours from the start
    of that horizon.  Orders are indivisible in the first allocation model;
    upstream consolidation may create the batches supplied here.
    """
    known_nodes = set(nodes)
    seen = set()
    normalized = []
    for raw in orders:
        row = dict(raw)
        required = {"order_id", "origin", "destination", "tonnes", "deadline_hours"}
        if not required <= row.keys():
            raise ValueError("allocation orders require id, endpoints, tonnes and deadline_hours")
        if not isinstance(row["order_id"], str) or not row["order_id"] or row["order_id"] in seen:
            raise ValueError("order_id must be unique and nonempty")
        seen.add(row["order_id"])
        if row["origin"] not in known_nodes or row["destination"] not in known_nodes:
            raise ValueError(f"unknown endpoint for order {row['order_id']}")
        if row["origin"] == row["destination"]:
            raise ValueError("order endpoints must differ")
        row["tonnes"] = _number(row["tonnes"], "order tonnes", positive=True)
        row["deadline_hours"] = _number(
            row["deadline_hours"], "order deadline_hours", positive=True)
        row["release_hour"] = _number(
            row.get("release_hour", 0), "order release_hour", nonnegative=True)
        if row["release_hour"] >= row["deadline_hours"]:
            raise ValueError("order release must precede its deadline")
        row["shipment_units"] = _number(
            row.get("shipment_units", 1), "order shipment_units", positive=True)
        row.setdefault("container_type", "unspecified")
        row.setdefault("cargo_type", "general")
        row.setdefault("source_type", "model_assumption")
        normalized.append(row)
    if not normalized:
        raise ValueError("at least one allocation order is required")
    return normalized


def normalize_departures(departures, edges):
    """Validate scheduled or planning-horizon capacity resources.

    A ``capacity_only`` row constrains aggregate use of an edge over the
    planning horizon without inventing a departure time. Timed rows model a
    concrete departure opportunity and affect both waiting and capacity.
    """
    edge_ids = {edge["id"] for edge in edges}
    seen = set()
    normalized = []
    for raw in departures:
        row = dict(raw)
        if not {"departure_id", "edge_id"} <= row.keys():
            raise ValueError("capacity resources require departure_id and edge_id")
        if not isinstance(row["departure_id"], str) or not row["departure_id"] or row["departure_id"] in seen:
            raise ValueError("departure_id must be unique and nonempty")
        seen.add(row["departure_id"])
        if row["edge_id"] not in edge_ids:
            raise ValueError(f"unknown departure edge: {row['edge_id']}")
        row["capacity_only"] = bool(row.get("capacity_only", False))
        if row["capacity_only"]:
            if row.get("departure_hour") is not None:
                raise ValueError("capacity-only resources must not set departure_hour")
            row["departure_hour"] = None
        else:
            if "departure_hour" not in row:
                raise ValueError("timed departures require departure_hour")
            row["departure_hour"] = _number(
                row["departure_hour"], "departure_hour", nonnegative=True)
        for field in ("capacity_tonnes", "capacity_units"):
            value = row.get(field)
            if value is not None:
                row[field] = _number(value, field, positive=True)
        if row.get("capacity_tonnes") is None and row.get("capacity_units") is None:
            raise ValueError("a departure requires tonnes or shipment-unit capacity")
        row["available"] = bool(row.get("available", True))
        row.setdefault("evidence_class", "model_assumption")
        normalized.append(row)
    return normalized


def _order_network(base_config, order):
    config = deepcopy(base_config)
    config["origin"] = order["origin"]
    config["destination"] = order["destination"]
    config["time_window_hours"] = [0, order["deadline_hours"]]
    # Candidate generation retains late alternatives.  Hard-deadline violation
    # is assessed from the explicit scheduled arrival below.
    config["hard_deadline"] = False
    config["emission_cap_kg"] = None
    config["risk_weight"] = 0
    config["scenarios"] = [{
        "name": f"allocation-{order['order_id']}",
        "tonnes": order["tonnes"],
        "shipment_units": order["shipment_units"],
        "probability": 1,
        "speed_multiplier": 1,
        "service_time_multiplier": 1,
        "rate_multiplier": 1,
    }]
    return Network(config)


def _route_timing_labels(network, route, order, departures_by_edge,
                         max_schedule_combinations):
    """Enumerate feasible departure combinations for one physical route."""
    states = [{"ready": order["release_hour"], "scheduled_wait": 0.0,
               "departure_ids": [], "capacity_claims": []}]
    previous_mode = None
    for edge_index in route:
        edge = network.edges[edge_index]
        next_states = []
        transfer_hours = 0.0
        if previous_mode is not None and previous_mode != edge["mode"]:
            transfer = network.transfer_at(edge["from"], previous_mode, edge["mode"])
            if transfer is None:
                return []
            transfer_hours = transfer["hours_per_1000_tonnes"] * order["tonnes"] / 1000
        duration = edge.get(
            "service_hours", edge["distance_km"] / network.modes[edge["mode"]]["speed_kmh"])
        duration += edge.get("handling_hours", 0)
        resources = departures_by_edge.get(edge["id"], ())
        scheduled = [row for row in resources if not row["capacity_only"]]
        capacity_only = [row for row in resources if row["capacity_only"]]
        horizon_claims = [{
            "departure_id": row["departure_id"],
            "tonnes": order["tonnes"],
            "shipment_units": order["shipment_units"],
        } for row in capacity_only]
        for state in states:
            connection_ready = state["ready"] + transfer_hours
            if scheduled:
                for departure in scheduled:
                    if not departure["available"] or departure["departure_hour"] < connection_ready:
                        continue
                    wait = departure["departure_hour"] - connection_ready
                    next_states.append({
                        "ready": departure["departure_hour"] + duration,
                        "scheduled_wait": state["scheduled_wait"] + wait,
                        "departure_ids": state["departure_ids"] + [departure["departure_id"]],
                        "capacity_claims": state["capacity_claims"] + horizon_claims + [{
                            "departure_id": departure["departure_id"],
                            "tonnes": order["tonnes"],
                            "shipment_units": order["shipment_units"],
                        }],
                    })
            else:
                assumed_wait = edge.get("scheduled_wait_hours", 0)
                next_states.append({
                    "ready": connection_ready + assumed_wait + duration,
                    "scheduled_wait": state["scheduled_wait"] + assumed_wait,
                    "departure_ids": list(state["departure_ids"]),
                    "capacity_claims": state["capacity_claims"] + horizon_claims,
                })
        next_states.sort(key=lambda row: (row["ready"], row["scheduled_wait"],
                                          row["departure_ids"]))
        states = next_states[:max_schedule_combinations]
        if not states:
            return []
        previous_mode = edge["mode"]
    return states


def _route_surrogate(network, order, route, next_edge):
    """Positive additive score used only to bound large-graph route search."""
    edge = network.edges[next_edge]
    transport = (edge["quoted_cost_cny_per_unit"] * order["shipment_units"]
                 if "quoted_cost_cny_per_unit" in edge else
                 edge["distance_km"] * network.mode_rate(edge["mode"], edge["distance_km"])
                 * order["tonnes"])
    emissions = (edge["distance_km"]
                 * network.modes[edge["mode"]]["emissions_kg_per_tonne_km"]
                 * order["tonnes"])
    transfer_cost = transfer_emissions = 0.0
    if route:
        previous_mode = network.edges[route[-1]]["mode"]
        if previous_mode != edge["mode"]:
            transfer = network.transfer_at(edge["from"], previous_mode, edge["mode"])
            if transfer is None:
                return math.inf
            transfer_cost = transfer["cost_cny_per_tonne"] * order["tonnes"]
            transfer_emissions = transfer["emissions_kg_per_tonne"] * order["tonnes"]
    return transport + transfer_cost + network.brackets[0][1] * (emissions + transfer_emissions)


def _beam_routes(network, order, *, limit, beam_width, allowed_modes=None):
    """Return bounded low-surrogate-cost city-simple routes for large graphs.

    This is candidate generation, not an optimality certificate. The global
    allocation still evaluates retained routes with the full cost model.
    """
    counter = 0
    frontier = [(0.0, counter, network.origin, None,
                 frozenset((network.origin,)), ())]
    complete = []
    for _depth in range(len(network.nodes) - 1):
        next_frontier = []
        for score, _, node, previous_mode, visited, route in frontier:
            for edge_index in network._choices(node, previous_mode, visited):
                edge = network.edges[edge_index]
                if allowed_modes is not None and edge["mode"] not in allowed_modes:
                    continue
                next_score = score + _route_surrogate(network, order, route, edge_index)
                next_route = route + (edge_index,)
                counter += 1
                if edge["to"] == network.destination:
                    complete.append((next_score, counter, next_route))
                else:
                    next_frontier.append((next_score, counter, edge["to"], edge["mode"],
                                          visited | {edge["to"]}, next_route))
        if not next_frontier:
            break
        frontier = heapq.nsmallest(beam_width, next_frontier)
        if len(complete) >= limit:
            threshold = heapq.nsmallest(limit, complete)[-1][0]
            if frontier[0][0] >= threshold:
                break
    return [row[2] for row in heapq.nsmallest(limit, complete)]


def _diverse_beam_routes(network, order, *, limit, beam_width):
    """Merge mode-specific and unrestricted beams without duplicate routes."""
    groups = ({"road"}, {"rail"}, {"water"}, None)
    per_group = max(1, math.ceil(limit / len(groups)))
    routes = []
    seen = set()
    for allowed_modes in groups:
        for route in _beam_routes(network, order, limit=per_group,
                                  beam_width=beam_width,
                                  allowed_modes=allowed_modes):
            if route not in seen:
                seen.add(route)
                routes.append(route)
    return routes[:limit]


def _retain_candidates(candidates, top_k):
    """Keep ranked choices and always preserve an unconstrained fallback."""
    original_rank = {row["candidate_id"]: index for index, row in enumerate(candidates)}
    retained = list(candidates[:top_k])
    fallback = next((row for row in candidates if not row["capacity_claims"]), None)
    if fallback is not None and fallback not in retained:
        if retained:
            retained[-1] = fallback
        else:
            retained.append(fallback)
        retained.sort(key=lambda row: original_rank[row["candidate_id"]])
    return retained


def generate_candidate_pools(base_config, orders, departures=(), *, top_k=5,
                             max_routes=5000, max_schedule_combinations=200,
                             route_strategy="auto", beam_width=500):
    """Generate ranked route-departure alternatives for every order.

    The ranking is a per-order surrogate only.  It uses the first marginal
    carbon rate and cannot account for shared capacity or aggregate carbon
    brackets; those deliberate omissions create the global allocation task.
    """
    for name, value in (("top_k", top_k), ("max_routes", max_routes),
                        ("max_schedule_combinations", max_schedule_combinations),
                        ("beam_width", beam_width)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if route_strategy not in {"auto", "enumerate", "beam"}:
        raise ValueError("route_strategy must be auto, enumerate or beam")
    normalized_orders = normalize_allocation_orders(orders, base_config["nodes"])
    normalized_departures = normalize_departures(departures, base_config["edges"])
    departures_by_edge = {}
    for row in normalized_departures:
        departures_by_edge.setdefault(row["edge_id"], []).append(row)
    for rows in departures_by_edge.values():
        rows.sort(key=lambda row: (row["departure_hour"] is None,
                                   row["departure_hour"] or 0, row["departure_id"]))

    pools = {}
    stats = {"orders": len(normalized_orders), "physical_route_order_pairs": 0,
             "physical_routes_by_order": {}, "route_departure_candidates": 0,
             "retained_candidates": 0, "top_k": top_k,
             "route_strategy_by_order": {}}
    for order in normalized_orders:
        network = _order_network(base_config, order)
        candidates = []
        strategy = ("enumerate" if len(network.nodes) <= 8 else "beam") if route_strategy == "auto" else route_strategy
        if strategy == "beam":
            routes = _diverse_beam_routes(
                network, order, limit=max_routes, beam_width=beam_width)
        else:
            try:
                routes = list(network.routes(max_states=max_routes))
            except RuntimeError as exc:
                raise RuntimeError(f"candidate route limit reached for {order['order_id']}") from exc
        stats["route_strategy_by_order"][order["order_id"]] = strategy
        stats["physical_route_order_pairs"] += len(routes)
        stats["physical_routes_by_order"][order["order_id"]] = len(routes)
        for route in routes:
            base = network.evaluate(route)
            scenario = base["scenarios"][0]
            timing_labels = _route_timing_labels(
                network, route, order, departures_by_edge, max_schedule_combinations)
            for label_index, timing in enumerate(timing_labels):
                lateness = max(0.0, timing["ready"] - order["deadline_hours"])
                waiting_cost = (timing["scheduled_wait"] * order["tonnes"]
                                * base_config.get("storage_cny_per_tonne_hour", 0))
                lateness_cost = (lateness * order["tonnes"]
                                 * base_config.get("late_penalty_cny_per_tonne_hour", 0))
                costs = {
                    "transport_cost_cny": scenario["transport_cost_cny"],
                    "transfer_cost_cny": scenario["transfer_cost_cny"],
                    "scheduled_wait_cost_cny": waiting_cost,
                    "lateness_cost_cny": lateness_cost,
                }
                noncarbon = math.fsum(costs.values())
                first_carbon = network.brackets[0][1] * scenario["emissions_kg"]
                edge_ids = [network.edges[index]["id"] for index in route]
                suffix = "+".join(timing["departure_ids"]) or f"ondemand-{label_index}"
                candidates.append({
                    "candidate_id": f"{order['order_id']}|{'>'.join(edge_ids)}|{suffix}",
                    "order_id": order["order_id"],
                    "edge_indices": list(route),
                    "edge_ids": edge_ids,
                    "route": base["route"],
                    "modes": base["modes"],
                    "departure_ids": timing["departure_ids"],
                    "capacity_claims": timing["capacity_claims"],
                    "arrival_hour": timing["ready"],
                    "scheduled_wait_hours": timing["scheduled_wait"],
                    "lateness_hours": lateness,
                    "intrinsic_violation": base["constraint_violation"],
                    "costs": costs,
                    "noncarbon_cost_cny": noncarbon,
                    "emissions_kg": scenario["emissions_kg"],
                    "surrogate_cost_cny": noncarbon + first_carbon,
                })
        candidates.sort(key=lambda row: (
            row["intrinsic_violation"] + row["lateness_hours"] / order["deadline_hours"],
            row["surrogate_cost_cny"], row["arrival_hour"], row["candidate_id"]))
        pools[order["order_id"]] = _retain_candidates(candidates, top_k)
        stats["route_departure_candidates"] += len(candidates)
        stats["retained_candidates"] += len(pools[order["order_id"]])
    return {
        "orders": normalized_orders,
        "departures": normalized_departures,
        "candidate_pools": pools,
        "generation_stats": stats,
    }


def evaluate_assignment(orders, candidate_pools, departures, chromosome, brackets):
    """Evaluate an order-to-candidate chromosome with shared capacities."""
    order_ids = [row["order_id"] for row in orders]
    if len(chromosome) != len(order_ids):
        raise ValueError("one allocation gene is required per order")
    capacities = {row["departure_id"]: row for row in departures}
    usage = {key: {"tonnes": 0.0, "shipment_units": 0.0} for key in capacities}
    selected = []
    invalid = 0
    intrinsic_violation = deadline_violation = 0.0
    costs = {"transport_cost_cny": 0.0, "transfer_cost_cny": 0.0,
             "scheduled_wait_cost_cny": 0.0, "lateness_cost_cny": 0.0}
    emissions = 0.0
    for order, gene in zip(orders, chromosome):
        pool = candidate_pools.get(order["order_id"], ())
        if isinstance(gene, bool) or not isinstance(gene, int) or not 0 <= gene < len(pool):
            invalid += 1
            continue
        candidate = pool[gene]
        selected.append(candidate)
        intrinsic_violation += candidate["intrinsic_violation"]
        deadline_violation += candidate["lateness_hours"] / max(1, order["deadline_hours"])
        for key in costs:
            costs[key] += candidate["costs"][key]
        emissions += candidate["emissions_kg"]
        for claim in candidate["capacity_claims"]:
            if claim["departure_id"] not in usage:
                invalid += 1
                continue
            usage[claim["departure_id"]]["tonnes"] += claim["tonnes"]
            usage[claim["departure_id"]]["shipment_units"] += claim["shipment_units"]

    capacity_violation = 0.0
    capacity_rows = []
    for departure_id, used in usage.items():
        capacity = capacities[departure_id]
        excess_tonnes = (max(0.0, used["tonnes"] - capacity["capacity_tonnes"])
                          if capacity.get("capacity_tonnes") is not None else 0.0)
        excess_units = (max(0.0, used["shipment_units"] - capacity["capacity_units"])
                        if capacity.get("capacity_units") is not None else 0.0)
        if capacity.get("capacity_tonnes") is not None:
            capacity_violation += excess_tonnes / capacity["capacity_tonnes"]
        if capacity.get("capacity_units") is not None:
            capacity_violation += excess_units / capacity["capacity_units"]
        capacity_rows.append({
            "departure_id": departure_id,
            "used_tonnes": used["tonnes"],
            "capacity_tonnes": capacity.get("capacity_tonnes"),
            "used_shipment_units": used["shipment_units"],
            "capacity_units": capacity.get("capacity_units"),
            "excess_tonnes": excess_tonnes,
            "excess_units": excess_units,
        })
    carbon = carbon_cost(emissions, _carbon_brackets(brackets))
    noncarbon = math.fsum(costs.values())
    violation = invalid + intrinsic_violation + deadline_violation + capacity_violation
    return {
        "chromosome": list(chromosome),
        "selected_candidates": selected,
        "assigned_orders": len(selected),
        "unassigned_orders": invalid,
        **costs,
        "noncarbon_cost_cny": noncarbon,
        "carbon_cost_cny": carbon,
        "total_cost_cny": noncarbon + carbon,
        "emissions_kg": emissions,
        "capacity_usage": capacity_rows,
        "intrinsic_violation": intrinsic_violation,
        "deadline_violation": deadline_violation,
        "capacity_violation": capacity_violation,
        "constraint_violation": violation,
        "feasible": math.isclose(violation, 0.0, abs_tol=1e-12),
    }


def assignment_rank(result):
    """Feasibility-first ordering shared by every allocation solver."""
    return (result["constraint_violation"], result["total_cost_cny"], result["emissions_kg"])


def solve_greedy_allocation(orders, candidate_pools, departures, brackets):
    """Earliest-deadline-first baseline with marginal global evaluation."""
    return _solve_ordered_greedy(
        orders, candidate_pools, departures, brackets,
        sorted(orders, key=lambda row: (
            row["deadline_hours"], row["release_hour"], row["order_id"])),
        "greedy-earliest-deadline")


def solve_opportunity_greedy_allocation(orders, candidate_pools, departures, brackets):
    """Prioritize orders with the largest absolute loss from scarce capacity.

    The score compares the cheapest locally feasible candidate with the
    cheapest candidate that claims no shared resource. It is a deterministic
    heuristic seed, not an optimality bound.
    """
    def opportunity_loss(order):
        candidates = [row for row in candidate_pools.get(order["order_id"], ())
                      if row["intrinsic_violation"] == 0 and row["lateness_hours"] == 0]
        if not candidates:
            return -math.inf
        best = min(row["surrogate_cost_cny"] for row in candidates)
        fallbacks = [row["surrogate_cost_cny"] for row in candidates
                     if not row["capacity_claims"]]
        fallback = min(fallbacks) if fallbacks else max(
            row["surrogate_cost_cny"] for row in candidates)
        return fallback - best

    sequence = sorted(orders, key=lambda row: (
        -opportunity_loss(row), row["deadline_hours"], row["release_hour"],
        row["order_id"]))
    return _solve_ordered_greedy(
        orders, candidate_pools, departures, brackets, sequence,
        "greedy-opportunity-cost")


def _solve_ordered_greedy(orders, candidate_pools, departures, brackets,
                          order_sequence, solver_name):
    """Assign a supplied order sequence by feasibility-first marginal rank."""
    position = {row["order_id"]: index for index, row in enumerate(orders)}
    chromosome = [0] * len(orders)
    fixed = set()
    for order in order_sequence:
        index = position[order["order_id"]]
        pool = candidate_pools.get(order["order_id"], ())
        if not pool:
            chromosome[index] = -1
            fixed.add(index)
            continue
        best_gene = None
        best_rank = None
        for gene in range(len(pool)):
            trial = list(chromosome)
            trial[index] = gene
            # Evaluate only assigned positions; neutralize future genes by using
            # a restricted problem so they do not influence the marginal rank.
            active_indices = sorted(fixed | {index})
            active_orders = [orders[i] for i in active_indices]
            active_genes = [trial[i] for i in active_indices]
            result = evaluate_assignment(
                active_orders, candidate_pools, departures, active_genes, brackets)
            rank = assignment_rank(result)
            if best_rank is None or rank < best_rank:
                best_gene, best_rank = gene, rank
        chromosome[index] = best_gene
        fixed.add(index)
    result = evaluate_assignment(orders, candidate_pools, departures, chromosome, brackets)
    return {"solver": solver_name, "status": (
        "feasible-heuristic" if result["feasible"] else "infeasible-allocation"),
            "solution": result, "candidate_evaluations": sum(
                len(candidate_pools.get(row["order_id"], ())) for row in orders)}


def solve_exact_allocation(orders, candidate_pools, departures, brackets,
                           max_combinations=1_000_000):
    """Enumerate small allocation instances to provide an optimality oracle."""
    if isinstance(max_combinations, bool) or not isinstance(max_combinations, int) or max_combinations < 1:
        raise ValueError("max_combinations must be a positive integer")
    option_counts = [len(candidate_pools.get(row["order_id"], ())) for row in orders]
    if any(count == 0 for count in option_counts):
        return {"solver": "exact-allocation-enumeration", "status": "infeasible",
                "solution": None, "candidate_evaluations": 0}
    combinations = math.prod(option_counts)
    if combinations > max_combinations:
        raise ValueError("exact allocation combination limit exceeded")
    best = None
    for chromosome in product(*(range(count) for count in option_counts)):
        result = evaluate_assignment(orders, candidate_pools, departures, chromosome, brackets)
        if result["feasible"] and (best is None or assignment_rank(result) < assignment_rank(best)):
            best = result
    return {"solver": "exact-allocation-enumeration",
            "status": "optimal" if best is not None else "infeasible",
            "solution": best, "candidate_evaluations": combinations}
