#!/usr/bin/env python3
"""Run a policy-calibrated experiment on the synthetic 23-city network.

The experiment reuses the corridor policy design's demand, release, payload,
deadline, carbon-price and reduction-target parameters.  It does not promote
those scenario inputs or the synthetic topology to observed operations.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import html
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.allocation import (assignment_rank, generate_candidate_pools,
                                solve_greedy_allocation)
from routing.allocation_ga import solve_allocation_ga
from routing.real_world import carbon_schedule
from routing.synthetic import generate_network
from tools.run_allocation_experiment import COLORS, percentile, svg, write_csv
from tools.run_synthetic_objective_matrix import (filter_candidate_pools,
                                                  solution_metrics)


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "data" / "policy_experiment.json"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "synthetic-23city-policy-matrix"
POLICY_VARIANTS = {
    "fixed": {
        "adaptive": False, "catastrophe": False, "heuristic_seed": False,
    },
    "adaptive": {
        "adaptive": True, "catastrophe": False, "heuristic_seed": False,
        "adaptive_control": "diversity-v2", "mutation_base": .75,
        "mutation_cap": 1.25, "patience": 30,
    },
    "catastrophe": {
        "adaptive": False, "catastrophe": True, "heuristic_seed": False,
        "patience": 12, "restart_fraction": .10,
    },
    "combined": {
        "adaptive": True, "catastrophe": True, "heuristic_seed": False,
        "adaptive_control": "diversity-v2", "mutation_base": .5,
        "mutation_cap": 1.0, "patience": 12, "restart_fraction": .10,
    },
    "hybrid-seeded": {
        "adaptive": True, "catastrophe": True, "heuristic_seed": True,
        "adaptive_control": "diversity-v2", "mutation_base": .5,
        "mutation_cap": 1.0, "patience": 12, "restart_fraction": .10,
        "heuristic_seed_mode": "archive",
        "heuristic_seed_strategy": "opportunity",
    },
}
METHODS = tuple(POLICY_VARIANTS)
TARGET_BASELINE_SCOPE = "single-mode-per-order"
TARGET_BASELINE_DEFINITION = (
    "per_order_minimum_cost_single_trunk_mode_same_scenario")
_WORKER_CONTEXT = None


def scenario_id(demand, time_profile, carbon_price, reduction, scope=None):
    price = str(carbon_price).replace(".", "p")
    target = str(round(reduction * 100, 1)).replace(".", "p")
    base = f"{demand}-{time_profile}-c{price}-r{target}"
    return f"{base}-{scope}" if scope else base


def generate_policy_portfolio(nodes, design, demand, time_profile):
    """Create multi-OD synthetic orders using the policy scenario parameters."""
    count = design["demand_profiles"][demand]
    seed = (design["synthetic_23city_extension"]["network"]["portfolio_seed"]
            + {"low": 1, "central": 2, "high": 3}[demand])
    rng = random.Random(seed)
    # Sample across the whole 23-city chain instead of forcing every order to
    # span from the first five to the last five cities.  The broader OD set is
    # required for the 48/60/72-hour service classes to distinguish short,
    # medium and long movements.
    origins = list(range(len(nodes) - 1))
    time_model = design["synthetic_23city_extension"]["operational_time_model"]
    deadline_model = time_model["deadline_model"]
    lead_time_values = deadline_model["lead_time_values_hours"]
    cargo_types = list(deadline_model["cargo_mix"])
    cargo_weights = [deadline_model["cargo_mix"][key] for key in cargo_types]
    node_positions = {node: index for index, node in enumerate(nodes)}
    span_thresholds = deadline_model["od_span_thresholds"]
    orders = []
    for index in range(count):
        origin_index = rng.choice(origins)
        destination_index = rng.randrange(origin_index + 1, len(nodes))
        release = rng.choice(design["release_hours"])
        cargo_type = rng.choices(cargo_types, weights=cargo_weights, k=1)[0]
        od_span = ((destination_index-origin_index) / max(1, len(nodes)-1))
        od_band = ("short" if od_span < span_thresholds[0] else
                   "medium" if od_span < span_thresholds[1] else "long")
        base_lead = deadline_model["base_lead_time_hours"][cargo_type][od_band]
        lead_index = lead_time_values.index(base_lead)
        lead_index = max(0, min(
            len(lead_time_values)-1,
            lead_index + deadline_model["profile_step"][time_profile]))
        lead_time = lead_time_values[lead_index]
        orders.append({
            "order_id": f"S23-{demand[0].upper()}{time_profile[0].upper()}-{index:03d}",
            "origin": nodes[origin_index],
            "destination": nodes[destination_index],
            "release_hour": release,
            "deadline_hours": release + lead_time,
            "lead_time_hours": lead_time,
            "od_distance_band": od_band,
            "od_span_fraction": od_span,
            "tonnes": rng.choice(design["payload_tonnes"]),
            "shipment_units": 1,
            "container_type": "20ft-model-unit",
            "cargo_type": cargo_type,
            "source_type": "policy_calibrated_synthetic_order",
        })
    return orders


def apply_operational_time_model(config, extension):
    """Attach explicit synthetic operational delays to every network edge."""
    time_model = extension["operational_time_model"]
    for edge in config["edges"]:
        service = time_model["mode_service"][edge["mode"]]
        edge["handling_hours"] = service["handling_hours_per_leg"]
        edge["port_dwell_hours"] = service["port_dwell_hours_per_leg"]
        edge["lock_delay_hours"] = (
            service["lock_delay_hours_per_1000_km"]
            * edge["distance_km"] / 1000)
        edge["reliability_buffer_hours"] = service[
            "reliability_buffer_hours_per_leg"]
        if service["scheduled_headway_hours"] is None:
            edge["scheduled_wait_hours"] = service[
                "assumed_dispatch_wait_hours"]
        else:
            edge.pop("scheduled_wait_hours", None)
    for transfer in config["transfers"]:
        key = "-".join(sorted(transfer["modes"]))
        transfer["fixed_hours"] = time_model["fixed_transfer_hours"][key]
    return config


def _departure_phase(edge, config, service):
    """Return a stable lane phase without relying on process-randomized hash()."""
    step = service["phase_step_hours"]
    headway = service["scheduled_headway_hours"]
    slots = max(1, round(headway / step))
    node_index = {node: index for index, node in enumerate(config["nodes"])}
    slot = (7*node_index[edge["from"]] + 11*node_index[edge["to"]]) % slots
    return slot * step


def policy_capacity_resources(config, extension, orders):
    """Create capacity resources, including capacity-limited water sailings."""
    mapping = extension["capacity_mapping"]
    time_model = extension["operational_time_model"]
    horizon = max(order["deadline_hours"] for order in orders)
    resources = []
    for edge in config["edges"]:
        if edge["mode"] not in mapping:
            continue
        service = time_model["mode_service"][edge["mode"]]
        headway = service["scheduled_headway_hours"]
        scheduled_capacity = time_model["scheduled_capacity"].get(edge["mode"])
        if headway is None or scheduled_capacity is None:
            resources.append({
                "departure_id": f'POLICY-S23-{edge["id"]}',
                "edge_id": edge["id"],
                "capacity_only": True,
                "capacity_tonnes": mapping[edge["mode"]]["capacity_tonnes"],
                "capacity_units": mapping[edge["mode"]]["capacity_units"],
                "evidence_class": "policy_scenario_calibrated_synthetic_capacity",
            })
            continue
        phase = _departure_phase(edge, config, service)
        departure_hour = phase
        while departure_hour <= horizon + headway:
            resources.append({
                "departure_id": f'POLICY-S23-{edge["id"]}-H{departure_hour:04.0f}',
                "edge_id": edge["id"],
                "departure_hour": departure_hour,
                "capacity_tonnes": scheduled_capacity[
                    "capacity_tonnes_per_departure"],
                "capacity_units": scheduled_capacity[
                    "capacity_units_per_departure"],
                "evidence_class": "policy_calibrated_synthetic_timed_departure",
            })
            departure_hour += headway
    return resources


def build_instance(base_config, design, demand, time_profile, carbon_price,
                   *, top_k, candidate_routes, beam_width):
    config = deepcopy(base_config)
    apply_operational_time_model(
        config, design["synthetic_23city_extension"])
    config["carbon_brackets"] = carbon_schedule(carbon_price)
    orders = generate_policy_portfolio(config["nodes"], design, demand, time_profile)
    resources = policy_capacity_resources(
        config, design["synthetic_23city_extension"], orders)
    generated = generate_candidate_pools(
        config, orders, resources, top_k=top_k, max_routes=candidate_routes,
        route_strategy="beam", beam_width=beam_width)
    return config, generated


def run_hybrid_screen(generated, brackets, settings, seeds, emission_cap_kg=None,
                      candidate_pools=None):
    pools = candidate_pools or generated["candidate_pools"]
    results = []
    for seed in seeds:
        controls = {
            "population": settings["population"],
            "generations": settings["generations"],
            "patience": settings.get("patience", 20),
            "seed": seed,
            "emission_cap_kg": emission_cap_kg,
        }
        controls.update(POLICY_VARIANTS["hybrid-seeded"])
        result = solve_allocation_ga(
            generated["orders"], pools,
            generated["departures"], brackets,
            **controls)
        results.append(result)
    feasible = [row for row in results if row["solution"] is not None]
    if feasible:
        return min(feasible, key=lambda row: assignment_rank(row["solution"]))
    return min(results, key=lambda row: assignment_rank(row["best_infeasible"]))


def solve_single_trunk_cost_baseline(generated, brackets, settings=None, seeds=None):
    """Return the per-order min of feasible pure road, rail and water routes.

    This reference implements ``min{water, rail, road}`` independently for
    each order under its own release/deadline constraints.  It deliberately
    excludes cross-order shared-capacity coupling; capacity remains a hard
    constraint in every evaluated allocation.  The distinction keeps the
    reference faithful to a traditional single-trunk choice rather than
    turning it into another portfolio-allocation result.
    """
    if len(brackets) != 1:
        raise ValueError("single-trunk baseline certificate requires linear carbon pricing")
    pools = filter_candidate_pools(generated["candidate_pools"], TARGET_BASELINE_SCOPE)
    if any(not pools[order["order_id"]] for order in generated["orders"]):
        raise RuntimeError("single-trunk baseline has an order without candidates")
    selected = []
    for order in generated["orders"]:
        feasible = [candidate for candidate in pools[order["order_id"]]
                    if candidate["intrinsic_violation"] == 0
                    and candidate["lateness_hours"] == 0]
        if not feasible:
            raise RuntimeError(
                f"single-trunk baseline has no deadline-feasible candidate for {order['order_id']}")
        selected.append(min(feasible, key=lambda candidate: (
            candidate["surrogate_cost_cny"], candidate["emissions_kg"],
            candidate["arrival_hour"], candidate["candidate_id"])))
    noncarbon = math.fsum(candidate["noncarbon_cost_cny"] for candidate in selected)
    emissions = math.fsum(candidate["emissions_kg"] for candidate in selected)
    carbon_rate = (brackets[0]["rate_cny_per_kg"]
                   if isinstance(brackets[0], dict) else brackets[0][1])
    carbon = emissions * carbon_rate
    baseline = {
        "selected_candidates": selected,
        "noncarbon_cost_cny": noncarbon,
        "carbon_cost_cny": carbon,
        "total_cost_cny": noncarbon + carbon,
        "emissions_kg": emissions,
        "feasible": True,
    }
    return baseline, {
        "transport_scope": TARGET_BASELINE_SCOPE,
        "definition": TARGET_BASELINE_DEFINITION,
        "candidate_objective_lower_bound_cny": baseline["total_cost_cny"],
        "optimality_status": "per-order-candidate-minimum-certified",
        "shared_capacity_in_reference": False,
    }


def screening_record(demand, time_profile, carbon_price, reduction,
                     generated, result, baseline, cap):
    solution = result["solution"] or result["best_infeasible"]
    metrics = solution_metrics(solution, generated["orders"])
    abated = baseline["emissions_kg"] - solution["emissions_kg"]
    emission_lower_bound = sum(
        min(candidate["emissions_kg"]
            for candidate in generated["candidate_pools"][row["order_id"]])
        for row in generated["orders"])
    return {
        "scenario_id": scenario_id(demand, time_profile, carbon_price, reduction),
        "demand": demand,
        "time_profile": time_profile,
        "carbon_price_cny_per_tco2e": carbon_price,
        "reduction_target": reduction,
        "orders": len(generated["orders"]),
        "tonnes": sum(row["tonnes"] for row in generated["orders"]),
        "baseline_cost_cny": baseline["total_cost_cny"],
        "baseline_emissions_kg": baseline["emissions_kg"],
        "baseline_definition": TARGET_BASELINE_DEFINITION,
        "baseline_transport_scope": TARGET_BASELINE_SCOPE,
        "emission_cap_kg": cap,
        "candidate_emissions_lower_bound_kg": emission_lower_bound,
        "maximum_candidate_reduction_percent": (
            (1-emission_lower_bound/baseline["emissions_kg"]) * 100),
        "status": result["status"],
        "feasible": result["solution"] is not None,
        "seed": result["seed"],
        "total_cost_cny": solution["total_cost_cny"],
        "noncarbon_cost_cny": solution["noncarbon_cost_cny"],
        "emissions_kg": solution["emissions_kg"],
        "achieved_reduction_percent": (
            abated / baseline["emissions_kg"] * 100),
        "total_cost_premium_percent": (
            (solution["total_cost_cny"] / baseline["total_cost_cny"] - 1) * 100),
        "tonne_weighted_transit_hours": metrics["tonne_weighted_transit_hours"],
        "tonne_weighted_travel_hours": metrics["tonne_weighted_travel_hours"],
        "tonne_weighted_handling_hours": metrics["tonne_weighted_handling_hours"],
        "tonne_weighted_port_dwell_hours": metrics["tonne_weighted_port_dwell_hours"],
        "tonne_weighted_lock_delay_hours": metrics["tonne_weighted_lock_delay_hours"],
        "tonne_weighted_reliability_buffer_hours": metrics[
            "tonne_weighted_reliability_buffer_hours"],
        "tonne_weighted_scheduled_wait_hours": metrics[
            "tonne_weighted_scheduled_wait_hours"],
        "tonne_weighted_transfer_hours": metrics["tonne_weighted_transfer_hours"],
        "used_water_departures": metrics["used_water_departures"],
        "water_departures_at_capacity": metrics["water_departures_at_capacity"],
        "max_water_departure_utilization": metrics[
            "max_water_departure_utilization"],
        "constraint_violation": solution["constraint_violation"],
        "candidate_evaluations": result["candidate_evaluations"],
    }


def screening_lower_bound_record(demand, time_profile, carbon_price, reduction,
                                 generated, baseline, cap, emission_lower_bound):
    """Record a cap below the sum of per-order minimum candidate emissions."""
    return {
        "scenario_id": scenario_id(demand, time_profile, carbon_price, reduction),
        "demand": demand, "time_profile": time_profile,
        "carbon_price_cny_per_tco2e": carbon_price,
        "reduction_target": reduction,
        "orders": len(generated["orders"]),
        "tonnes": sum(row["tonnes"] for row in generated["orders"]),
        "baseline_cost_cny": baseline["total_cost_cny"],
        "baseline_emissions_kg": baseline["emissions_kg"],
        "baseline_definition": TARGET_BASELINE_DEFINITION,
        "baseline_transport_scope": TARGET_BASELINE_SCOPE,
        "emission_cap_kg": cap,
        "candidate_emissions_lower_bound_kg": emission_lower_bound,
        "maximum_candidate_reduction_percent": (
            (1-emission_lower_bound/baseline["emissions_kg"]) * 100),
        "status": "infeasible-candidate-emission-lower-bound",
        "feasible": False, "seed": None, "total_cost_cny": None,
        "noncarbon_cost_cny": None, "emissions_kg": None,
        "achieved_reduction_percent": None,
        "total_cost_premium_percent": None,
        "tonne_weighted_transit_hours": None,
        "constraint_violation": None, "candidate_evaluations": 0,
    }


def _initialize_worker(orders, pools, departures, brackets, settings):
    global _WORKER_CONTEXT
    _WORKER_CONTEXT = (orders, pools, departures, brackets, settings)


def _solve_worker(task):
    method, controls, seed = task
    orders, pools, departures, brackets, settings = _WORKER_CONTEXT
    solver_settings = dict(settings)
    solver_settings.update(controls)
    result = solve_allocation_ga(
        orders, pools, departures, brackets, seed=seed, **solver_settings)
    return method, seed, result


def formal_record(sid, scope, reduction, method, seed, result, orders):
    solution = result["solution"] or result.get("best_infeasible")
    metrics = solution_metrics(solution, orders) if solution else {}
    return {
        "scenario_id": sid,
        "transport_scope": scope,
        "reduction_target": reduction,
        "method": method,
        "seed": seed,
        "status": result["status"],
        "feasible": result["solution"] is not None,
        "total_cost_cny": solution["total_cost_cny"] if solution else None,
        "emissions_kg": solution["emissions_kg"] if solution else None,
        "tonne_weighted_transit_hours": metrics.get("tonne_weighted_transit_hours"),
        "tonne_weighted_travel_hours": metrics.get("tonne_weighted_travel_hours"),
        "tonne_weighted_handling_hours": metrics.get("tonne_weighted_handling_hours"),
        "tonne_weighted_port_dwell_hours": metrics.get(
            "tonne_weighted_port_dwell_hours"),
        "tonne_weighted_lock_delay_hours": metrics.get(
            "tonne_weighted_lock_delay_hours"),
        "tonne_weighted_reliability_buffer_hours": metrics.get(
            "tonne_weighted_reliability_buffer_hours"),
        "tonne_weighted_scheduled_wait_hours": metrics.get(
            "tonne_weighted_scheduled_wait_hours"),
        "tonne_weighted_transfer_hours": metrics.get("tonne_weighted_transfer_hours"),
        "used_water_departures": metrics.get("used_water_departures"),
        "water_departures_at_capacity": metrics.get("water_departures_at_capacity"),
        "max_water_departure_utilization": metrics.get(
            "max_water_departure_utilization"),
        "constraint_violation": solution["constraint_violation"] if solution else None,
        "emission_violation": solution["emission_violation"] if solution else None,
        "restarts": result.get("restarts", 0),
        "candidate_evaluations": result.get("candidate_evaluations", 0),
    }


def run_formal_scenario(generated, brackets, scope, reduction, cap, settings,
                        seeds, workers):
    pools = filter_candidate_pools(generated["candidate_pools"], scope)
    sid = scenario_id(settings["demand"], settings["time_profile"],
                      settings["carbon_price_cny_per_tco2e"], reduction, scope)
    empty_orders = [row["order_id"] for row in generated["orders"]
                    if not pools[row["order_id"]]]
    if empty_orders:
        return [{
            "scenario_id": sid, "transport_scope": scope,
            "reduction_target": reduction, "method": method, "seed": seed,
            "status": "infeasible-no-candidates", "feasible": False,
            "total_cost_cny": None, "emissions_kg": None,
            "tonne_weighted_transit_hours": None, "constraint_violation": None,
            "emission_violation": None, "restarts": 0,
            "candidate_evaluations": 0,
        } for method in METHODS for seed in seeds]
    emission_lower_bound = sum(
        min(candidate["emissions_kg"] for candidate in pools[row["order_id"]])
        for row in generated["orders"])
    if cap is not None and emission_lower_bound > cap + 1e-9:
        return [{
            "scenario_id": sid, "transport_scope": scope,
            "reduction_target": reduction, "method": method, "seed": seed,
            "status": "infeasible-candidate-emission-lower-bound",
            "feasible": False, "total_cost_cny": None, "emissions_kg": None,
            "tonne_weighted_transit_hours": None,
            "constraint_violation": None, "emission_violation": None,
            "restarts": 0, "candidate_evaluations": 0,
        } for method in METHODS for seed in seeds]
    solver_settings = {
        "population": settings["population"],
        "generations": settings["generations"],
        "patience": settings["patience"],
        "emission_cap_kg": cap,
    }
    tasks = [(method, controls, seed)
             for method, controls in POLICY_VARIANTS.items() for seed in seeds]
    if workers == 1:
        _initialize_worker(generated["orders"], pools, generated["departures"],
                           brackets, solver_settings)
        solved = map(_solve_worker, tasks)
        executor = None
    else:
        executor = ProcessPoolExecutor(
            max_workers=workers, initializer=_initialize_worker,
            initargs=(generated["orders"], pools, generated["departures"],
                      brackets, solver_settings))
        solved = executor.map(_solve_worker, tasks, chunksize=1)
    try:
        return [formal_record(sid, scope, reduction, method, seed, result,
                              generated["orders"])
                for method, seed, result in solved]
    finally:
        if executor is not None:
            executor.shutdown()


def summarize_formal(runs, scenarios):
    summaries = []
    for scenario in scenarios:
        for method in METHODS:
            selected = [row for row in runs
                        if row["scenario_id"] == scenario["scenario_id"]
                        and row["method"] == method]
            feasible = [row for row in selected if row["feasible"]]
            costs = [row["total_cost_cny"] for row in feasible]
            times = [row["tonne_weighted_transit_hours"] for row in feasible]
            emissions = [row["emissions_kg"] for row in feasible]
            summaries.append({
                **scenario,
                "method": method,
                "runs": len(selected),
                "feasible_runs": len(feasible),
                "feasible_rate": len(feasible) / len(selected) if selected else 0,
                "best_cost_cny": min(costs) if costs else None,
                "median_cost_cny": statistics.median(costs) if costs else None,
                "q1_cost_cny": percentile(costs, .25) if costs else None,
                "q3_cost_cny": percentile(costs, .75) if costs else None,
                "median_transit_hours": statistics.median(times) if times else None,
                "median_emissions_kg": statistics.median(emissions) if emissions else None,
                "mean_restarts": statistics.fmean(row["restarts"] for row in selected),
            })
    return summaries


def _marker(method, x, y):
    color = COLORS[method]
    if method == "fixed":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{color}"/>'
    if method == "adaptive":
        return (f'<rect x="{x-5:.1f}" y="{y-5:.1f}" width="10" height="10" '
                f'fill="{color}"/>')
    if method == "catastrophe":
        return (f'<polygon points="{x:.1f},{y-6:.1f} {x+6:.1f},{y:.1f} '
                f'{x:.1f},{y+6:.1f} {x-6:.1f},{y:.1f}" fill="{color}"/>')
    if method == "combined":
        return (f'<polygon points="{x:.1f},{y-6:.1f} {x+6:.1f},{y+5:.1f} '
                f'{x-6:.1f},{y+5:.1f}" fill="{color}"/>')
    return (f'<polygon points="{x-6:.1f},{y:.1f} {x-3:.1f},{y-5.2:.1f} '
            f'{x+3:.1f},{y-5.2:.1f} {x+6:.1f},{y:.1f} '
            f'{x+3:.1f},{y+5.2:.1f} {x-3:.1f},{y+5.2:.1f}" fill="{color}"/>')


def write_screening_sensitivity(path, screening):
    """Show whether policy targets change cost under demand, time and price cases."""
    panels = [
        ("Demand", "demand", ("low", "central", "high"),
         lambda row: row["time_profile"] == "balanced"
         and row["carbon_price_cny_per_tco2e"] == 97.49),
        ("Deadline", "time_profile", ("tight", "balanced", "relaxed"),
         lambda row: row["demand"] == "central"
         and row["carbon_price_cny_per_tco2e"] == 97.49),
        ("Carbon shadow price", "carbon_price_cny_per_tco2e", (0.0, 97.49, 6000.0),
         lambda row: row["demand"] == "central"
         and row["time_profile"] == "balanced"),
    ]
    colors = ("#4c78a8", "#f58518", "#54a24b")
    chosen = [row for _, _, _, predicate in panels for row in screening
              if predicate(row) and row["feasible"]]
    values = [row["total_cost_premium_percent"] for row in chosen]
    y_min = math.floor((min(values)-.25) * 2) / 2
    y_max = math.ceil((max(values)+.25) * 2) / 2
    width, height = 1380, 540
    body = []
    for panel_index, (title, field, categories, predicate) in enumerate(panels):
        left = 85 + panel_index * 445
        top, panel_w, panel_h = 110, 355, 320
        body.append(f'<rect x="{left}" y="{top}" width="{panel_w}" height="{panel_h}" fill="none" stroke="#777"/>')
        body.append(f'<text x="{left+panel_w/2:.1f}" y="78" text-anchor="middle" font-family="sans-serif" font-size="13">{title}</text>')
        for category_index, category in enumerate(categories):
            rows = sorted((row for row in screening
                           if predicate(row) and row[field] == category
                           and row["feasible"]),
                          key=lambda row: row["reduction_target"])
            points = []
            for row in rows:
                x = left + row["reduction_target"] / .3 * panel_w
                y = top + panel_h - ((row["total_cost_premium_percent"]-y_min)
                                     / max(1e-12, y_max-y_min) * panel_h)
                points.append(f"{x:.1f},{y:.1f}")
                body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{colors[category_index]}"/>')
            body.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[category_index]}" stroke-width="2"/>')
            legend_x = left + category_index * 118
            label = f"{category:g}" if isinstance(category, float) else str(category)
            body.append(f'<line x1="{legend_x}" y1="468" x2="{legend_x+18}" y2="468" stroke="{colors[category_index]}" stroke-width="3"/>')
            body.append(f'<text x="{legend_x+24}" y="472" font-family="sans-serif" font-size="10">{label}</text>')
        for target in (0, .095, .2, .3):
            x = left + target / .3 * panel_w
            body.append(f'<text x="{x:.1f}" y="450" text-anchor="middle" font-family="sans-serif" font-size="10">{target*100:g}%</text>')
        for fraction in (0, .5, 1):
            value = y_min + fraction * (y_max-y_min)
            y = top + panel_h - fraction * panel_h
            body.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{value:.1f}%</text>')
    body.append('<text x="690" y="520" text-anchor="middle" font-family="sans-serif" font-size="12">Reduction target relative to per-order minimum-cost single-trunk emissions</text>')
    body.append('<text x="22" y="270" transform="rotate(-90 22 270)" text-anchor="middle" font-family="sans-serif" font-size="12">Total model-cost change versus cost optimum (%)</text>')
    path.write_text(svg(
        "23-city policy screening: per-order minimum-cost single-trunk reference", "".join(body),
        width=width, height=height,
        metadata={"data": "screening-grid.csv", "rows": len(screening),
                  "classification": "policy-calibrated synthetic"}), encoding="utf-8")


def write_formal_cost_time(path, summaries):
    """Compare five methods across candidate scopes and policy targets."""
    nonroad = [row for row in summaries
               if row["transport_scope"] != "road-only"
               and row["median_cost_cny"] is not None]
    cost_values = [row["median_cost_cny"] / 1000 for row in nonroad]
    time_values = [row["median_transit_hours"] for row in nonroad]
    cost_min = math.floor((min(cost_values)-.5) * 2) / 2
    cost_max = math.ceil((max(cost_values)+.5) * 2) / 2
    time_min = math.floor((min(time_values)-.25) * 2) / 2
    time_max = math.ceil((max(time_values)+.25) * 2) / 2
    width, height = 1380, 1040
    cost_left, cost_right = 250, 750
    time_left, time_right = 900, 1325

    def scaled(value, low, high, left, right):
        return left + (value-low) / max(1e-12, high-low) * (right-left)

    body = []
    for index, method in enumerate(METHODS):
        x = 250 + index * 205
        body.append(_marker(method, x, 73))
        body.append(f'<text x="{x+12}" y="77" font-family="sans-serif" font-size="11">{method}</text>')
    body.extend([
        '<text x="500" y="118" text-anchor="middle" font-family="sans-serif" font-size="13">Median cost (thousand CNY)</text>',
        '<text x="1112" y="118" text-anchor="middle" font-family="sans-serif" font-size="13">Median tonne-weighted transit time (hours)</text>',
    ])
    for fraction in range(5):
        cost = cost_min + fraction * (cost_max-cost_min) / 4
        x = scaled(cost, cost_min, cost_max, cost_left, cost_right)
        duration = time_min + fraction * (time_max-time_min) / 4
        tx = scaled(duration, time_min, time_max, time_left, time_right)
        body.append(f'<line x1="{x:.1f}" y1="132" x2="{x:.1f}" y2="900" stroke="#ddd"/>')
        body.append(f'<text x="{x:.1f}" y="144" text-anchor="middle" font-family="sans-serif" font-size="10">{cost:.1f}</text>')
        body.append(f'<line x1="{tx:.1f}" y1="132" x2="{tx:.1f}" y2="900" stroke="#ddd"/>')
        body.append(f'<text x="{tx:.1f}" y="144" text-anchor="middle" font-family="sans-serif" font-size="10">{duration:.1f}</text>')
    road = next(row for row in summaries
                if row["transport_scope"] == "road-only"
                and row["reduction_target"] == 0
                and row["method"] == "hybrid-seeded")
    body.append('<text x="20" y="170" font-family="sans-serif" font-size="12" font-weight="bold">Road-only, uncapped</text>')
    body.append(f'<text x="250" y="170" font-family="sans-serif" font-size="12">all methods overlap: CNY {road["median_cost_cny"]/1000:.1f}k | {road["median_transit_hours"]:.2f} h</text>')
    included = []
    for scope, label in (("single-mode-per-order", "No transfer"),
                         ("multimodal-enabled", "Multimodal")):
        for target in (0, .095, .2, .3):
            included.append((scope, target, label))
    offsets = {method: -16 + index * 8 for index, method in enumerate(METHODS)}
    for row_index, (scope, target, label) in enumerate(included):
        y = 235 + row_index * 82
        rows = [row for row in summaries if row["transport_scope"] == scope
                and row["reduction_target"] == target]
        body.append(f'<text x="20" y="{y-3}" font-family="sans-serif" font-size="12" font-weight="bold">{label}</text>')
        body.append(f'<text x="20" y="{y+14}" font-family="sans-serif" font-size="11">target {target*100:g}%</text>')
        body.append(f'<line x1="{cost_left}" y1="{y}" x2="{cost_right}" y2="{y}" stroke="#bbb"/>')
        body.append(f'<line x1="{time_left}" y1="{y}" x2="{time_right}" y2="{y}" stroke="#bbb"/>')
        feasible_rows = [row for row in rows if row["median_cost_cny"] is not None]
        if not feasible_rows:
            body.append(f'<text x="{cost_left}" y="{y+4}" font-family="sans-serif" font-size="11">no feasible run</text>')
            body.append(f'<text x="{time_left}" y="{y+4}" font-family="sans-serif" font-size="11">no feasible run</text>')
            continue
        best = min(feasible_rows, key=lambda row: row["median_cost_cny"])
        for row in feasible_rows:
            marker_y = y + offsets[row["method"]]
            cost = row["median_cost_cny"] / 1000
            duration = row["median_transit_hours"]
            x = scaled(cost, cost_min, cost_max, cost_left, cost_right)
            tx = scaled(duration, time_min, time_max, time_left, time_right)
            body.append(_marker(row["method"], x, marker_y))
            body.append(_marker(row["method"], tx, marker_y))
            if row is best:
                body.append(f'<text x="{x+9:.1f}" y="{marker_y+4:.1f}" font-family="sans-serif" font-size="10">{cost:.1f}k</text>')
                body.append(f'<text x="{tx+9:.1f}" y="{marker_y+4:.1f}" font-family="sans-serif" font-size="10">{duration:.2f} h</text>')
    positive_targets = sorted({row["reduction_target"] for row in summaries
                               if row["transport_scope"] != "road-only"
                               and row["reduction_target"] > 0})
    feasibility_text = []
    for target in positive_targets:
        target_rows = [row for row in summaries
                       if row["transport_scope"] != "road-only"
                       and row["reduction_target"] == target]
        feasible_runs = sum(row["feasible_runs"] for row in target_rows)
        total_runs = sum(row["runs"] for row in target_rows)
        feasibility_text.append(
            f"{target*100:g}%: {feasible_runs}/{total_runs}")
    body.extend([
        '<line x1="20" y1="925" x2="1325" y2="925" stroke="#bbb"/>',
        '<text x="20" y="952" font-family="sans-serif" font-size="12" font-weight="bold">Positive-target feasibility</text>',
        f'<text x="250" y="952" font-family="sans-serif" font-size="12">{html.escape(" | ".join(feasibility_text))} feasible nonroad runs</text>',
        f'<text x="250" y="987" font-family="sans-serif" font-size="10">Road-only positive targets are omitted from the panels when infeasible; all caps use the common per-order minimum-cost single-trunk reference.</text>',
    ])
    path.write_text(svg(
        "Policy-calibrated 23-city GA comparison (tuned controls)", "".join(body),
        width=width, height=height,
        metadata={"data": "method-scenario-summary.csv", "methods": METHODS,
                  "tuning": "../synthetic-23city-policy-tuning/results.json",
                  "classification": "policy-calibrated synthetic"}), encoding="utf-8")


def parse_csv_arg(raw, cast=str):
    return [cast(value.strip()) for value in raw.split(",") if value.strip()]


def run(args):
    design = json.loads(args.design.read_text(encoding="utf-8"))
    extension = design["synthetic_23city_extension"]
    network_settings = extension["network"]
    base_config = generate_network(
        network_settings["nodes"], network_settings["density"],
        network_settings["seed"])
    args.output.mkdir(parents=True, exist_ok=True)

    screening_settings = dict(design["algorithm_screening"])
    screening_settings["population"] = args.screening_population
    screening_settings["generations"] = args.screening_generations
    instance_cache = {}
    baselines = {}
    screening = []
    for demand in args.demands:
        for time_profile in args.time_profiles:
            for carbon_price in args.carbon_prices:
                key = (demand, time_profile, carbon_price)
                config, generated = build_instance(
                    base_config, design, demand, time_profile, carbon_price,
                    top_k=args.top_k, candidate_routes=args.candidate_routes,
                    beam_width=args.beam_width)
                instance_cache[key] = (config, generated)
                baseline, baseline_meta = solve_single_trunk_cost_baseline(
                    generated, config["carbon_brackets"], screening_settings,
                    args.screening_seeds)
                baselines[key] = baseline
                emission_lower_bound = sum(
                    min(candidate["emissions_kg"] for candidate in
                        generated["candidate_pools"][row["order_id"]])
                    for row in generated["orders"])
                for reduction in args.reduction_targets:
                    cap = (None if reduction == 0 else
                           baseline["emissions_kg"] * (1-reduction))
                    if cap is not None and emission_lower_bound > cap + 1e-9:
                        screening.append(screening_lower_bound_record(
                            demand, time_profile, carbon_price, reduction,
                            generated, baseline, cap, emission_lower_bound))
                        continue
                    result = run_hybrid_screen(
                        generated, config["carbon_brackets"], screening_settings,
                        args.screening_seeds, emission_cap_kg=cap)
                    screening.append(screening_record(
                        demand, time_profile, carbon_price, reduction,
                        generated, result, baseline, cap))

    core = dict(extension["formal_core"])
    core["population"] = args.formal_population
    core["generations"] = args.formal_generations
    core_key = (core["demand"], core["time_profile"],
                core["carbon_price_cny_per_tco2e"])
    if core_key not in instance_cache:
        instance_cache[core_key] = build_instance(
            base_config, design, *core_key, top_k=args.top_k,
            candidate_routes=args.candidate_routes, beam_width=args.beam_width)
        config, generated = instance_cache[core_key]
        baseline, _ = solve_single_trunk_cost_baseline(
            generated, config["carbon_brackets"], screening_settings,
            args.screening_seeds)
        baselines[core_key] = baseline
    config, generated = instance_cache[core_key]
    baseline = baselines[core_key]
    _, baseline_meta = solve_single_trunk_cost_baseline(
        generated, config["carbon_brackets"], screening_settings,
        args.screening_seeds)
    formal_runs = []
    formal_scenarios = []
    for scope in args.scopes:
        for reduction in args.formal_targets:
            cap = (None if reduction == 0 else
                   baseline["emissions_kg"] * (1-reduction))
            sid = scenario_id(*core_key, reduction, scope)
            scenario = {
                "scenario_id": sid,
                "transport_scope": scope,
                "reduction_target": reduction,
                "emission_cap_kg": cap,
                "baseline_emissions_kg": baseline["emissions_kg"],
                "baseline_cost_cny": baseline["total_cost_cny"],
                "baseline_definition": TARGET_BASELINE_DEFINITION,
                "baseline_transport_scope": TARGET_BASELINE_SCOPE,
                "baseline_optimality_status": baseline_meta["optimality_status"],
                "baseline_candidate_objective_lower_bound_cny": (
                    baseline_meta["candidate_objective_lower_bound_cny"]),
            }
            formal_scenarios.append(scenario)
            formal_runs.extend(run_formal_scenario(
                generated, config["carbon_brackets"], scope, reduction, cap,
                core, args.formal_seeds, args.workers))
    summaries = summarize_formal(formal_runs, formal_scenarios)

    write_csv(args.output / "screening-grid.csv", screening)
    write_csv(args.output / "formal-runs.csv", formal_runs)
    write_csv(args.output / "method-scenario-summary.csv", summaries)
    write_screening_sensitivity(args.output / "policy-screening-sensitivity.svg", screening)
    write_formal_cost_time(args.output / "scope-ga-cost-time.svg", summaries)
    report = {
        "experiment_id": extension["experiment_id"],
        "data_classification": "policy_calibrated_synthetic",
        "evidence_boundary": extension["evidence_boundary"],
        "network": {
            "nodes": len(base_config["nodes"]),
            "edges": len(base_config["edges"]),
            "density": network_settings["density"],
            "seed": network_settings["seed"],
        },
        "reused_policy_parameters": {
            "demand_profiles": design["demand_profiles"],
            "deadline_model": extension["operational_time_model"]["deadline_model"],
            "release_hours": design["release_hours"],
            "payload_tonnes": design["payload_tonnes"],
            "carbon_shadow_prices_cny_per_tco2e": args.carbon_prices,
            "emissions_reduction_targets": args.reduction_targets,
            "policy_anchors": design["policy_anchors"],
            "capacity_mapping": extension["capacity_mapping"],
            "operational_time_model": extension["operational_time_model"],
        },
        "screening": {
            "rows": len(screening),
            "method": "hybrid-seeded",
            "seeds": args.screening_seeds,
            "population": args.screening_population,
            "generations": args.screening_generations,
            "results": screening,
        },
        "formal_comparison": {
            "core": core,
            "transport_scopes": args.scopes,
            "reduction_targets": args.formal_targets,
            "methods": list(METHODS),
            "variant_controls": POLICY_VARIANTS,
            "hyperparameter_selection": {
                "record": "../synthetic-23city-policy-tuning/results.json",
                "tuning_seeds": list(range(100, 108)),
                "validation_seeds": list(range(110, 130)),
                "formal_seeds": args.formal_seeds,
            },
            "seeds": args.formal_seeds,
            "runs": len(formal_runs),
            "scenarios": formal_scenarios,
            "method_scenario_summary": summaries,
        },
        "emissions_target_reference": {
            "transport_scope": TARGET_BASELINE_SCOPE,
            "definition": TARGET_BASELINE_DEFINITION,
            "interpretation": (
                "independently select each order's minimum-cost deadline-feasible "
                "candidate over retained pure-road, pure-rail and pure-water routes"),
            "direct_definition": (
                "no mode transfer; a mode-pure route may traverse multiple network nodes"),
            "shared_capacity_in_reference": False,
            "capacity_interpretation": (
                "the reference is an independent per-order comparator; shared "
                "capacity is enforced in every evaluated allocation"),
            **baseline_meta,
        },
        "claims": [
            "The 23-city topology and every order remain synthetic; policy inputs calibrate scenarios rather than create observed operations.",
            "The 9.5, 20 and 30 percent targets are policy-inspired stress percentages, not shipment-level legal caps.",
            "Each positive cap is defined from the uncapped cost-optimal single-trunk-mode emissions in the same demand, deadline and carbon-price scenario.",
            "The reference independently minimizes each order over retained pure-road, pure-rail and pure-water candidates; every order uses one trunk mode and no mode transfer.",
            "Cross-order shared capacity is excluded from the reference comparator and remains enforced in every evaluated allocation.",
            "Road-only, single-mode and multimodal-enabled results all use this common single-trunk emissions denominator.",
            "Water uses discrete 24-hour synthetic sailings with 20-tonne and two-unit capacity per departure; waiting is calculated from each order's release and connection-ready time.",
            "Travel, handling, port dwell, lock delay, reliability buffer, scheduled waiting and fixed-plus-volume transfer time are accumulated separately and all count toward the hard deadline.",
            "Order lead times are 48, 60 or 72 hours and are assigned from synthetic OD-distance and cargo-class rules, with tight/balanced/relaxed profiles shifting one service-class step.",
            "A cap below the sum of per-order minimum candidate emissions is certified infeasible within the retained candidate pools without running the GA.",
            "Lower-bound failures prove infeasibility only within retained candidate pools; other no-feasible heuristic results are not infeasibility proofs.",
        ],
    }
    (args.output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    feasible_screening = sum(row["feasible"] for row in screening)
    feasible_formal = sum(row["feasible"] for row in formal_runs)
    certified_formal = sum(
        row["status"] == "infeasible-candidate-emission-lower-bound"
        for row in formal_runs)
    searched_infeasible_formal = (len(formal_runs) - feasible_formal
                                  - certified_formal)
    (args.output / "README.md").write_text(f"""# Synthetic 23-city policy-calibrated matrix

Generated by `python3 -B tools/run_synthetic_policy_matrix.py`.

This experiment reuses the corridor policy design's demand, release, payload, carbon-price and reduction-target parameters on the synthetic 23-city topology. Deadlines are now assigned by OD span and cargo class at 48, 60 or 72 hours. Water operates on explicit 24-hour synthetic sailings capped at 20 tonnes and two shipment units per departure. Travel, terminal handling, port dwell, lock delay, reliability buffer, schedule waiting and mode-transfer time all count toward feasibility. These operating values are policy-calibrated synthetic assumptions, not carrier commitments.

Each reduction cap is measured from a common traditional-transport reference: each order independently chooses its lowest-cost deadline-feasible candidate among pure-road, pure-rail and pure-water routes. A mode-pure route may traverse several network nodes but cannot transfer between modes. Cross-order shared capacity is excluded from this reference comparator and remains enforced in every evaluated allocation.

Mutation and restart controls were selected on seeds 100--107, verified on seeds 110--129 and then frozen before this formal seed 0--29 run. See the [separate tuning record](../synthetic-23city-policy-tuning/README.md).

The screening stage contains {feasible_screening}/{len(screening)} feasible cells. The formal matrix contains {feasible_formal} feasible solved records, {certified_formal} records certified infeasible by the retained-candidate emissions lower bound, and {searched_infeasible_formal} heuristic runs with no feasible allocation found. GA execution is skipped only for the certified cells. These are synthetic-input findings, not operational or legal claims.

- `screening-grid.csv`: demand x deadline x carbon-price x policy-target screening.
- `formal-runs.csv`: five-GA run-level results across candidate scopes and targets.
- `method-scenario-summary.csv`: comparable feasibility, cost, emissions and transit-time summaries.
- `policy-screening-sensitivity.svg`: demand, deadline and carbon-price sensitivity across policy targets.
- `scope-ga-cost-time.svg`: five-GA cost and transit-time comparison across route scopes and targets.
- `results.json`: complete design, reused inputs, evidence boundary and summaries.
""", encoding="utf-8")
    return report


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=DESIGN_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demands", default="low,central,high")
    parser.add_argument("--time-profiles", default="tight,balanced,relaxed")
    parser.add_argument("--carbon-prices", default="0,97.49,6000")
    parser.add_argument("--reduction-targets", default="0,0.095,0.2,0.3")
    parser.add_argument("--scopes", default="road-only,single-mode-per-order,multimodal-enabled")
    parser.add_argument("--formal-targets", default="0,0.095,0.2,0.3")
    parser.add_argument("--screening-seeds", default="70,71,72")
    parser.add_argument("--formal-seeds", default=",".join(str(value) for value in range(30)))
    parser.add_argument("--screening-population", type=int, default=40)
    parser.add_argument("--screening-generations", type=int, default=60)
    parser.add_argument("--formal-population", type=int, default=40)
    parser.add_argument("--formal-generations", type=int, default=60)
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--candidate-routes", type=int, default=80)
    parser.add_argument("--beam-width", type=int, default=300)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    args.demands = parse_csv_arg(args.demands)
    args.time_profiles = parse_csv_arg(args.time_profiles)
    args.carbon_prices = parse_csv_arg(args.carbon_prices, float)
    args.reduction_targets = parse_csv_arg(args.reduction_targets, float)
    args.scopes = parse_csv_arg(args.scopes)
    args.formal_targets = parse_csv_arg(args.formal_targets, float)
    args.screening_seeds = parse_csv_arg(args.screening_seeds, int)
    args.formal_seeds = parse_csv_arg(args.formal_seeds, int)
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    return args


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        "experiment_id": result["experiment_id"],
        "screening_rows": result["screening"]["rows"],
        "formal_runs": result["formal_comparison"]["runs"],
    }, indent=2, ensure_ascii=False))
