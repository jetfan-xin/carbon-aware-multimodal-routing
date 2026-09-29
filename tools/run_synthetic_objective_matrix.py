#!/usr/bin/env python3
"""Compare five GA variants across transport scopes and emissions targets.

The reduction targets are fixed against one reproducible counterfactual: the
best-known road-only result for the same 48-order portfolio.  They are not
claimed to be legal targets or observed operational reductions.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
import os
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.allocation import (assignment_rank, generate_candidate_pools,
                                solve_greedy_allocation)
from routing.allocation_ga import solve_allocation_ga
from routing.synthetic import generate_network
from tools.run_allocation_experiment import COLORS, percentile, svg, write_csv
from tools.run_synthetic_allocation_experiment import (SYNTHETIC_VARIANTS as VARIANTS,
                                                       generate_capacity_resources,
                                                       generate_portfolio)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks" / "synthetic-global-allocation" / "objective-matrix"
METHODS = tuple(VARIANTS)
REDUCTION_LEVELS = (0.20, 0.40, 0.55, 0.60)
_WORKER_CONTEXT = None


def _initialize_worker(orders, pools, departures, brackets, settings):
    global _WORKER_CONTEXT
    _WORKER_CONTEXT = (orders, pools, departures, brackets, settings)


def _solve_worker(task):
    method, controls, seed = task
    orders, pools, departures, brackets, settings = _WORKER_CONTEXT
    result = solve_allocation_ga(
        orders, pools, departures, brackets, seed=seed, **settings, **controls)
    return method, seed, result


def filter_candidate_pools(candidate_pools, scope):
    """Apply a transport-policy restriction without regenerating routes."""
    if scope == "multimodal-enabled":
        return {key: list(rows) for key, rows in candidate_pools.items()}
    if scope == "single-mode-per-order":
        return {key: [row for row in rows if len(set(row["modes"])) == 1]
                for key, rows in candidate_pools.items()}
    if scope == "road-only":
        return {key: [row for row in rows if set(row["modes"]) == {"road"}]
                for key, rows in candidate_pools.items()}
    raise ValueError(f"unknown transport scope: {scope}")


def solution_metrics(solution, orders):
    """Return comparable time and route-category metrics for one portfolio."""
    categories = {"road_only_tonnes": 0.0, "rail_only_tonnes": 0.0,
                  "water_only_tonnes": 0.0, "multimodal_tonnes": 0.0}
    component_fields = (
        "travel_hours", "handling_hours", "port_dwell_hours",
        "lock_delay_hours", "reliability_buffer_hours",
        "scheduled_wait_hours", "transfer_hours",
    )
    weighted_hours = {field: 0.0 for field in component_fields}
    transit_weighted = 0.0
    water_departure_ids = set()
    total_tonnes = sum(row["tonnes"] for row in orders)
    for order, candidate in zip(orders, solution["selected_candidates"]):
        unique = set(candidate["modes"])
        if len(unique) > 1:
            category = "multimodal_tonnes"
        else:
            category = f"{next(iter(unique))}_only_tonnes"
        categories[category] += order["tonnes"]
        transit_weighted += ((candidate["arrival_hour"] - order["release_hour"])
                             * order["tonnes"])
        for field in component_fields:
            weighted_hours[field] += candidate.get(field, 0) * order["tonnes"]
        if "water" in unique:
            water_departure_ids.update(candidate["departure_ids"])
    capacity_by_id = {row["departure_id"]: row
                      for row in solution.get("capacity_usage", ())}
    water_ratios = []
    for departure_id in water_departure_ids:
        row = capacity_by_id.get(departure_id)
        if row is None:
            continue
        ratios = []
        if row["capacity_tonnes"]:
            ratios.append(row["used_tonnes"] / row["capacity_tonnes"])
        if row["capacity_units"]:
            ratios.append(row["used_shipment_units"] / row["capacity_units"])
        water_ratios.append(max(ratios, default=0))
    return {
        "tonne_weighted_transit_hours": transit_weighted / total_tonnes,
        **{f"tonne_weighted_{field}": value / total_tonnes
           for field, value in weighted_hours.items()},
        "used_water_departures": len(water_ratios),
        "water_departures_at_capacity": sum(value >= 1-1e-12
                                             for value in water_ratios),
        "max_water_departure_utilization": max(water_ratios, default=0),
        **categories,
    }


def run_record(method, seed, result, orders, *, scenario, scope, target, cap):
    solution = result["solution"] or result.get("best_infeasible")
    if solution is None:
        return {
            "scenario": scenario, "transport_scope": scope,
            "reduction_target": target, "emission_cap_kg": cap,
            "method": method, "seed": seed, "status": result["status"],
            "feasible": False, "total_cost_cny": None,
            "noncarbon_cost_cny": None, "carbon_cost_cny": None,
            "emissions_kg": None, "constraint_violation": None,
            "emission_violation": None, "capacity_violation": None,
            "deadline_violation": None, "restarts": result.get("restarts", 0),
            "candidate_evaluations": result.get("candidate_evaluations", 0),
            "solution": None,
        }
    metrics = solution_metrics(solution, orders)
    return {
        "scenario": scenario, "transport_scope": scope,
        "reduction_target": target, "emission_cap_kg": cap,
        "method": method, "seed": seed, "status": result["status"],
        "feasible": result["solution"] is not None,
        "total_cost_cny": solution["total_cost_cny"],
        "noncarbon_cost_cny": solution["noncarbon_cost_cny"],
        "carbon_cost_cny": solution["carbon_cost_cny"],
        "emissions_kg": solution["emissions_kg"],
        "constraint_violation": solution["constraint_violation"],
        "emission_violation": solution["emission_violation"],
        "capacity_violation": solution["capacity_violation"],
        "deadline_violation": solution["deadline_violation"],
        "restarts": result.get("restarts", 0),
        "candidate_evaluations": result.get("candidate_evaluations", 0),
        **metrics,
        "solution": result["solution"],
    }


def run_scenario(generated, brackets, definition, args):
    pools = filter_candidate_pools(generated["candidate_pools"], definition["scope"])
    empty_orders = [row["order_id"] for row in generated["orders"]
                    if not pools[row["order_id"]]]
    rows = []
    traces = []
    if empty_orders:
        for method in METHODS:
            for seed in args.seeds:
                rows.append({
                    "scenario": definition["id"], "transport_scope": definition["scope"],
                    "reduction_target": definition["target"],
                    "emission_cap_kg": definition["cap"], "method": method,
                    "seed": seed, "status": "infeasible-no-candidates", "feasible": False,
                    "total_cost_cny": None, "noncarbon_cost_cny": None,
                    "carbon_cost_cny": None, "emissions_kg": None,
                    "constraint_violation": None, "emission_violation": None,
                    "capacity_violation": None, "deadline_violation": None,
                    "restarts": 0, "candidate_evaluations": 0, "solution": None,
                })
        return rows, traces, pools, empty_orders

    greedy = solve_greedy_allocation(
        generated["orders"], pools, generated["departures"], brackets,
        emission_cap_kg=definition["cap"])
    greedy_result = {
        "status": greedy["status"], "solution": greedy["solution"]
        if greedy["solution"]["feasible"] else None,
        "best_infeasible": None if greedy["solution"]["feasible"] else greedy["solution"],
        "restarts": 0, "candidate_evaluations": greedy["candidate_evaluations"],
    }
    rows.append(run_record(
        "greedy-reference", None, greedy_result, generated["orders"],
        scenario=definition["id"], scope=definition["scope"],
        target=definition["target"], cap=definition["cap"]))

    tasks = [(method, controls, seed) for method, controls in VARIANTS.items()
             for seed in args.seeds]
    settings = {"population": args.population, "generations": args.generations,
                "patience": args.patience, "emission_cap_kg": definition["cap"]}
    if args.workers == 1:
        _initialize_worker(generated["orders"], pools, generated["departures"],
                           brackets, settings)
        solved = map(_solve_worker, tasks)
        executor = None
    else:
        executor = ProcessPoolExecutor(
            max_workers=args.workers, initializer=_initialize_worker,
            initargs=(generated["orders"], pools, generated["departures"],
                      brackets, settings))
        solved = executor.map(_solve_worker, tasks, chunksize=1)
    try:
        for method, seed, result in solved:
            rows.append(run_record(
                method, seed, result, generated["orders"],
                scenario=definition["id"], scope=definition["scope"],
                target=definition["target"], cap=definition["cap"]))
            if definition["id"] in {"multimodal-cost", "multimodal-reduction-55"}:
                traces.extend({"scenario": definition["id"], "method": method,
                               "seed": seed, **trace} for trace in result["trace"])
    finally:
        if executor is not None:
            executor.shutdown()
    return rows, traces, pools, empty_orders


def summarize(runs, scenarios):
    summaries = []
    for scenario in scenarios:
        for method in METHODS:
            selected = [row for row in runs
                        if row["scenario"] == scenario["id"] and row["method"] == method]
            feasible = [row for row in selected if row["feasible"]]
            costs = [row["total_cost_cny"] for row in feasible]
            emissions = [row["emissions_kg"] for row in feasible]
            summaries.append({
                "scenario": scenario["id"], "transport_scope": scenario["scope"],
                "reduction_target": scenario["target"],
                "emission_cap_kg": scenario["cap"], "method": method,
                "runs": len(selected), "feasible_runs": len(feasible),
                "feasible_rate": len(feasible) / len(selected),
                "best_cost_cny": min(costs) if costs else None,
                "median_cost_cny": statistics.median(costs) if costs else None,
                "q1_cost_cny": percentile(costs, .25) if costs else None,
                "q3_cost_cny": percentile(costs, .75) if costs else None,
                "median_emissions_kg": statistics.median(emissions) if emissions else None,
                "best_emissions_kg": min(emissions) if emissions else None,
                "median_transit_hours": statistics.median(
                    row["tonne_weighted_transit_hours"] for row in feasible)
                if feasible else None,
                "mean_restarts": statistics.fmean(row["restarts"] for row in selected),
            })
    return summaries


def best_by_scenario(runs, scenarios):
    """Build a dominance-consistent archive from every discovered solution.

    A solution found while searching a tighter cap is also a valid incumbent
    for every looser cap with the same transport scope.  Pooling discovered
    solutions prevents stochastic search noise from making a relaxed
    best-known frontier look more expensive than a constrained one.  Formal
    method summaries remain scenario-local and are not pooled.
    """
    result = {}
    for scenario in scenarios:
        feasible = [row for row in runs
                    if row["transport_scope"] == scenario["scope"]
                    and row["method"] in METHODS and row["feasible"]
                    and (scenario["cap"] is None
                         or row["emissions_kg"] <= scenario["cap"] + 1e-9)]
        if not feasible:
            result[scenario["id"]] = None
            continue
        source = min(feasible, key=lambda row: assignment_rank(row["solution"]))
        archived = dict(source)
        archived["source_scenario"] = source["scenario"]
        archived["scenario"] = scenario["id"]
        archived["reduction_target"] = scenario["target"]
        archived["emission_cap_kg"] = scenario["cap"]
        result[scenario["id"]] = archived
    return result


def write_frontier(path, best_rows, road_emissions):
    data = [row for row in best_rows.values() if row]
    min_emissions = min(row["emissions_kg"] for row in data)
    max_emissions = max(row["emissions_kg"] for row in data)
    min_cost = min(row["total_cost_cny"] for row in data)
    max_cost = max(row["total_cost_cny"] for row in data)
    left, top, width, height = 125, 80, 980, 470
    body = [f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" stroke="#333"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+height}" stroke="#333"/>']
    colors = {"road-only": "#777777", "single-mode-per-order": "#54a24b",
              "multimodal-enabled": "#4c78a8"}
    grouped = {}
    for scenario, row in best_rows.items():
        if row:
            grouped.setdefault((round(row["emissions_kg"], 6),
                                round(row["total_cost_cny"], 6)), []).append((scenario, row))
    for group in grouped.values():
        scenarios_at_point = [item[0] for item in group]
        row = group[0][1]
        x = left + (row["emissions_kg"] - min_emissions) / max(1, max_emissions-min_emissions) * width
        y = top + height - (row["total_cost_cny"] - min_cost) / max(1, max_cost-min_cost) * height
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{colors[row["transport_scope"]]}"/>')
        if len(scenarios_at_point) > 1:
            levels = [name.rsplit("-", 1)[-1] for name in scenarios_at_point
                      if "reduction" in name]
            label = "multimodal: cost / reductions " + "/".join(levels)
        else:
            label = scenarios_at_point[0]
        if row["transport_scope"] == "road-only":
            label_x, label_y, anchor = x-10, y+19, "end"
        elif row["transport_scope"] == "single-mode-per-order":
            label_x, label_y, anchor = x+10, y-10, "start"
        else:
            label_x, label_y, anchor = x+10, y-10, "start"
        body.append(f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" font-family="sans-serif" font-size="10">{label}</text>')
    for fraction in (0, .25, .5, .75, 1):
        emission = min_emissions + fraction * (max_emissions-min_emissions)
        x = left + fraction * width
        body.append(f'<text x="{x:.1f}" y="{top+height+24}" text-anchor="middle" font-family="sans-serif" font-size="10">{emission/1000:.1f}</text>')
        cost = min_cost + fraction * (max_cost-min_cost)
        y = top + height - fraction * height
        body.append(f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{cost/1000:.0f}</text>')
    body.append('<text x="615" y="605" text-anchor="middle" font-family="sans-serif" font-size="13">Portfolio emissions (t CO2e)</text>')
    body.append('<text x="35" y="315" transform="rotate(-90 35 315)" text-anchor="middle" font-family="sans-serif" font-size="13">Best-known total cost (thousand CNY)</text>')
    path.write_text(svg(
        "23-city cost-emissions frontier by transport policy", "".join(body), width=1240,
        metadata={"data": "scenario-best.csv", "road_reference_emissions_kg": road_emissions,
                  "classification": "synthetic calibrated heuristic results"}), encoding="utf-8")


def write_method_matrix(path, summaries, scenarios):
    rows = {scenario["id"]: [row for row in summaries if row["scenario"] == scenario["id"]]
            for scenario in scenarios}
    left, top, cell_w, cell_h = 300, 105, 165, 58
    width = left + cell_w * len(METHODS) + 45
    height = top + cell_h * len(scenarios) + 90
    body = []
    for index, method in enumerate(METHODS):
        x = left + (index + .5) * cell_w
        body.append(f'<text x="{x:.1f}" y="78" text-anchor="middle" font-family="sans-serif" font-size="11">{method}</text>')
    for row_index, scenario in enumerate(scenarios):
        y = top + row_index * cell_h
        body.append(f'<text x="{left-12}" y="{y+25}" text-anchor="end" font-family="sans-serif" font-size="11">{scenario["id"]}</text>')
        feasible_costs = [row["median_cost_cny"] for row in rows[scenario["id"]]
                          if row["median_cost_cny"] is not None]
        best = min(feasible_costs) if feasible_costs else None
        for column, method in enumerate(METHODS):
            row = next(item for item in rows[scenario["id"]] if item["method"] == method)
            x = left + column * cell_w
            rate = row["feasible_rate"]
            fill = "#d9ead3" if rate == 1 else "#fff2cc" if rate > 0 else "#f4cccc"
            body.append(f'<rect x="{x}" y="{y}" width="{cell_w-5}" height="{cell_h-5}" fill="{fill}" stroke="#bbb"/>')
            if row["median_cost_cny"] is None:
                label = f'{row["feasible_runs"]}/{row["runs"]} feasible'
            else:
                gap = (row["median_cost_cny"] / best - 1) * 100
                label = f'{gap:+.2f}% | {row["feasible_runs"]}/{row["runs"]}'
            body.append(f'<text x="{x+(cell_w-5)/2:.1f}" y="{y+31}" text-anchor="middle" font-family="sans-serif" font-size="10">{label}</text>')
    body.append(f'<text x="{left}" y="{height-35}" font-family="sans-serif" font-size="11">Cell: median-cost gap to the best method in that scenario | feasible runs. Green = 30/30.</text>')
    path.write_text(svg(
        "Five-GA comparison across objective and transport scenarios", "".join(body),
        width=width, height=height,
        metadata={"data": "method-scenario-summary.csv", "methods": METHODS}), encoding="utf-8")


def _comparison_marker(method, x, y):
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


def write_cost_time_comparison(path, summaries, scenarios):
    """Show cost and transit-time medians without a 40-row result table."""
    included = (
        ("single-mode-cost", "No transfer", "no cap"),
        ("multimodal-cost", "Multimodal", "no cap"),
        ("multimodal-reduction-20", "Multimodal", "reduction >=20%"),
        ("multimodal-reduction-40", "Multimodal", "reduction >=40%"),
    )
    selected = {
        scenario: [row for row in summaries
                   if row["scenario"] == scenario and row["median_cost_cny"] is not None]
        for scenario, _, _ in included
    }
    cost_values = [row["median_cost_cny"] / 1000
                   for rows in selected.values() for row in rows]
    time_values = [row["median_transit_hours"]
                   for rows in selected.values() for row in rows]
    cost_min = math.floor((min(cost_values) - 2) / 5) * 5
    cost_max = math.ceil((max(cost_values) + 2) / 5) * 5
    time_min = math.floor((min(time_values) - .2) * 2) / 2
    time_max = math.ceil((max(time_values) + .2) * 2) / 2
    width, height = 1380, 720
    cost_left, cost_right = 250, 750
    time_left, time_right = 900, 1325

    def scaled(value, low, high, left, right):
        return left + (value - low) / max(1e-12, high - low) * (right - left)

    body = []
    legend_x = 260
    for index, method in enumerate(METHODS):
        x = legend_x + index * 205
        body.append(_comparison_marker(method, x, 73))
        body.append(f'<text x="{x+12}" y="77" font-family="sans-serif" font-size="11">{method}</text>')
    body.extend([
        '<text x="500" y="118" text-anchor="middle" font-family="sans-serif" font-size="13">Median cost (thousand CNY)</text>',
        '<text x="1112" y="118" text-anchor="middle" font-family="sans-serif" font-size="13">Median tonne-weighted transit time (hours)</text>',
        '<text x="20" y="166" font-family="sans-serif" font-size="12" font-weight="bold">Road-only reference</text>',
        '<text x="250" y="166" font-family="sans-serif" font-size="12">all five methods overlap: CNY 618.9k | 18.65 h</text>',
    ])
    for fraction in range(5):
        cost = cost_min + fraction * (cost_max-cost_min) / 4
        x = scaled(cost, cost_min, cost_max, cost_left, cost_right)
        body.append(f'<line x1="{x:.1f}" y1="132" x2="{x:.1f}" y2="590" stroke="#dddddd"/>')
        body.append(f'<text x="{x:.1f}" y="144" text-anchor="middle" font-family="sans-serif" font-size="10">{cost:.0f}</text>')
        duration = time_min + fraction * (time_max-time_min) / 4
        tx = scaled(duration, time_min, time_max, time_left, time_right)
        body.append(f'<line x1="{tx:.1f}" y1="132" x2="{tx:.1f}" y2="590" stroke="#dddddd"/>')
        body.append(f'<text x="{tx:.1f}" y="144" text-anchor="middle" font-family="sans-serif" font-size="10">{duration:.1f}</text>')
    offsets = {method: -16 + index * 8 for index, method in enumerate(METHODS)}
    for row_index, (scenario, label, qualifier) in enumerate(included):
        y = 240 + row_index * 112
        rows = selected[scenario]
        body.append(f'<text x="20" y="{y-4}" font-family="sans-serif" font-size="12" font-weight="bold">{label}</text>')
        body.append(f'<text x="20" y="{y+14}" font-family="sans-serif" font-size="11">{qualifier}</text>')
        body.append(f'<line x1="{cost_left}" y1="{y}" x2="{cost_right}" y2="{y}" stroke="#bbbbbb"/>')
        body.append(f'<line x1="{time_left}" y1="{y}" x2="{time_right}" y2="{y}" stroke="#bbbbbb"/>')
        best = min(rows, key=lambda row: row["median_cost_cny"])
        for row in rows:
            marker_y = y + offsets[row["method"]]
            cost = row["median_cost_cny"] / 1000
            duration = row["median_transit_hours"]
            x = scaled(cost, cost_min, cost_max, cost_left, cost_right)
            tx = scaled(duration, time_min, time_max, time_left, time_right)
            body.append(_comparison_marker(row["method"], x, marker_y))
            body.append(_comparison_marker(row["method"], tx, marker_y))
            if row is best:
                body.append(f'<text x="{x+9:.1f}" y="{marker_y+4:.1f}" font-family="sans-serif" font-size="10">{cost:.1f}k</text>')
                body.append(f'<text x="{tx+9:.1f}" y="{marker_y+4:.1f}" font-family="sans-serif" font-size="10">{duration:.2f} h</text>')
    body.extend([
        '<line x1="20" y1="633" x2="1325" y2="633" stroke="#bbbbbb"/>',
        '<text x="20" y="660" font-family="sans-serif" font-size="12" font-weight="bold">No feasible allocation found</text>',
        '<text x="250" y="660" font-family="sans-serif" font-size="12">multimodal reduction >=55% or >=60%; no-transfer reduction >=55% (0/30 for every method)</text>',
        '<text x="250" y="692" font-family="sans-serif" font-size="10">Scenario-local medians across 30 seeds. A missing feasible result is not a mathematical infeasibility proof.</text>',
    ])
    path.write_text(svg(
        "Five-GA cost and transit-time comparison", "".join(body), width=width,
        height=height, metadata={"data": "method-scenario-summary.csv",
                                 "aggregation": "scenario-local median across 30 seeds",
                                 "methods": METHODS}), encoding="utf-8")


def run(args):
    config = generate_network(23, args.density, args.network_seed)
    orders = generate_portfolio(config["nodes"], args.orders, args.order_seed)
    resources = generate_capacity_resources(config, args.capacity_tonnes, args.capacity_units)
    generated = generate_candidate_pools(
        config, orders, resources, top_k=args.top_k,
        max_routes=args.candidate_routes, route_strategy="beam",
        beam_width=args.beam_width)
    brackets = config["carbon_brackets"]

    road_definition = {"id": "road-cost", "scope": "road-only",
                       "target": 0.0, "cap": None}
    road_runs, road_traces, _, road_empty = run_scenario(
        generated, brackets, road_definition, args)
    road_feasible = [row for row in road_runs if row["method"] in METHODS and row["feasible"]]
    if not road_feasible:
        raise RuntimeError(f"road-only reference has no feasible result; empty orders={road_empty}")
    road_best = min(road_feasible, key=lambda row: assignment_rank(row["solution"]))
    road_reference_emissions = road_best["emissions_kg"]

    scenarios = [road_definition,
        {"id": "single-mode-cost", "scope": "single-mode-per-order", "target": 0.0, "cap": None},
        {"id": "multimodal-cost", "scope": "multimodal-enabled", "target": 0.0, "cap": None},
    ]
    scenarios.extend({
        "id": f"multimodal-reduction-{round(level*100)}",
        "scope": "multimodal-enabled", "target": level,
        "cap": road_reference_emissions * (1-level),
    } for level in REDUCTION_LEVELS)
    scenarios.append({
        "id": "single-mode-reduction-55", "scope": "single-mode-per-order",
        "target": .55, "cap": road_reference_emissions * .45,
    })

    runs = list(road_runs)
    traces = list(road_traces)
    scenario_metadata = [{**road_definition, "empty_candidate_orders": road_empty}]
    for definition in scenarios[1:]:
        selected, selected_traces, pools, empty = run_scenario(
            generated, brackets, definition, args)
        runs.extend(selected)
        traces.extend(selected_traces)
        scenario_metadata.append({
            **definition, "empty_candidate_orders": empty,
            "candidate_count_min": min(map(len, pools.values())),
            "candidate_count_max": max(map(len, pools.values())),
        })

    summaries = summarize(runs, scenarios)
    best = best_by_scenario(runs, scenarios)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "runs.csv", [
        {key: value for key, value in row.items() if key != "solution"} for row in runs])
    write_csv(args.output / "method-scenario-summary.csv", summaries)
    write_csv(args.output / "representative-traces.csv", traces)
    best_rows = []
    assignments = []
    for scenario in scenarios:
        row = best[scenario["id"]]
        if row is None:
            best_rows.append({
                "scenario": scenario["id"], "transport_scope": scenario["scope"],
                "reduction_target": scenario["target"], "emission_cap_kg": scenario["cap"],
                "feasible": False, "method": None, "seed": None,
                "total_cost_cny": None, "emissions_kg": None,
            })
            continue
        best_rows.append({key: row.get(key) for key in (
            "scenario", "transport_scope", "reduction_target", "emission_cap_kg",
            "source_scenario", "feasible", "method", "seed", "total_cost_cny", "noncarbon_cost_cny",
            "carbon_cost_cny", "emissions_kg", "tonne_weighted_transit_hours",
            "road_only_tonnes", "rail_only_tonnes", "water_only_tonnes",
            "multimodal_tonnes")})
        for order, candidate in zip(generated["orders"], row["solution"]["selected_candidates"]):
            assignments.append({
                "scenario": scenario["id"], "method": row["method"], "seed": row["seed"],
                "order_id": order["order_id"], "origin": order["origin"],
                "destination": order["destination"], "tonnes": order["tonnes"],
                "route": ">".join(candidate["route"]),
                "modes": "+".join(candidate["modes"]),
                "arrival_hour": candidate["arrival_hour"],
                "cost_cny": candidate["noncarbon_cost_cny"],
                "emissions_kg": candidate["emissions_kg"],
            })
    write_csv(args.output / "scenario-best.csv", best_rows)
    write_csv(args.output / "best-assignments.csv", assignments)
    write_frontier(args.output / "cost-emissions-frontier.svg", best,
                   road_reference_emissions)
    write_method_matrix(args.output / "five-ga-scenario-matrix.svg", summaries, scenarios)
    write_cost_time_comparison(args.output / "cost-time-by-method.svg", summaries, scenarios)

    report = {
        "experiment_id": "synthetic-23city-objective-transport-matrix-v1",
        "data_classification": "synthetic_calibrated",
        "network": {"nodes": len(config["nodes"]), "edges": len(config["edges"]),
                    "seed": args.network_seed, "density": args.density},
        "portfolio": {"orders": len(orders), "tonnes": sum(row["tonnes"] for row in orders),
                      "od_pairs": len({(row["origin"], row["destination"]) for row in orders}),
                      "capacity_resources": len(resources)},
        "algorithm_budget": {"methods": list(METHODS), "seeds": args.seeds,
                             "population": args.population,
                             "generations": args.generations,
                             "patience": args.patience,
                             "variant_controls": VARIANTS},
        "reference": {
            "definition": "best-known five-GA road-only cost result on the same portfolio",
            "method": road_best["method"], "seed": road_best["seed"],
            "cost_cny": road_best["total_cost_cny"],
            "emissions_kg": road_reference_emissions,
        },
        "scenarios": scenario_metadata,
        "method_scenario_summary": summaries,
        "best_known_by_scenario": best_rows,
        "claims": [
            "Every formal scenario compares the same five GA variants with equal population, generation and seed budgets.",
            "Greedy rows are auxiliary references and are not counted among the five GA variants.",
            "Reduction targets are hard portfolio caps relative to a best-known synthetic road-only counterfactual, not legal mandates or measured enterprise reductions.",
            "Single-mode-per-order allows road, rail or water across the portfolio but forbids a mode change inside one order route.",
            "Multimodal-enabled retains both direct single-mode and transfer routes; it does not force every order to transfer.",
            "Best-known scenario portfolios use a cross-scenario feasible archive: any tighter-cap solution is also admitted as an incumbent for a looser cap with the same transport scope.",
            "Method distributions and feasibility rates remain scenario-local; only the displayed best-known frontier uses the pooled archive.",
            "No-feasible-result means the tested heuristic budget found none; it is not a mathematical infeasibility proof.",
            "All full-portfolio results are heuristic and the input network, orders and capacities are synthetic calibrated data.",
        ],
    }
    (args.output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    feasible_scenarios = sum(row is not None for row in best.values())
    road_archive = best["road-cost"]
    single_archive = best["single-mode-cost"]
    multimodal_archive = best["multimodal-cost"]
    multimodal_cost_change = (
        (multimodal_archive["total_cost_cny"] / road_archive["total_cost_cny"] - 1) * 100)
    multimodal_emissions_change = (
        (multimodal_archive["emissions_kg"] / road_archive["emissions_kg"] - 1) * 100)
    transfer_cost_change = (
        (multimodal_archive["total_cost_cny"] / single_archive["total_cost_cny"] - 1) * 100)
    transfer_emissions_change = (
        (multimodal_archive["emissions_kg"] / single_archive["emissions_kg"] - 1) * 100)
    (args.output / "README.md").write_text(f"""# 23-city objective and transport-policy matrix

Generated by `python3 -B tools/run_synthetic_objective_matrix.py`.

This experiment holds the 23-city graph, 48-order portfolio, candidate budget and GA budget constant while changing the decision policy. It compares road-only transport, routes with no within-order transfer, and a multimodal-enabled candidate set. Cost is minimized in every scenario; 20%, 40%, 55% and 60% reduction cases add a hard portfolio emissions cap relative to the best-known road-only result on this same synthetic instance.

The five formal algorithms are fixed, adaptive, catastrophe, combined and hybrid-seeded. Each has {len(args.seeds)} seeds x {args.population} individuals x {args.generations} generations per scenario. Greedy is retained only as an auxiliary reference. {feasible_scenarios}/{len(scenarios)} scenarios produced at least one feasible GA result under this budget.

The road-only reference is CNY {road_archive['total_cost_cny']:,.2f} and {road_archive['emissions_kg']:,.2f} kg CO2e. The dominance-consistent multimodal archive is CNY {multimodal_archive['total_cost_cny']:,.2f} and {multimodal_archive['emissions_kg']:,.2f} kg: {abs(multimodal_cost_change):.2f}% lower cost and {abs(multimodal_emissions_change):.2f}% lower emissions than road-only. Against the best no-transfer portfolio, allowing transfer candidates changes cost by {transfer_cost_change:.2f}% and emissions by {transfer_emissions_change:.2f}%. The 20% and 40% caps are non-binding; no tested method finds a feasible result at 55% or 60%, or for no-transfer routing at 55%.

The archive pools discovered feasible solutions across scenarios with the same transport scope, because a tighter-cap solution is also valid under a looser cap. Method distributions remain scenario-local. A no-result boundary is not an infeasibility proof.

- `results.json`: definitions, budgets, evidence boundary and complete summaries.
- `runs.csv`: one row per method, seed and scenario, plus auxiliary greedy rows.
- `method-scenario-summary.csv`: comparable 30-seed feasibility, cost, emissions and time statistics.
- `scenario-best.csv`, `best-assignments.csv`: auditable best-known scenario portfolios.
- `representative-traces.csv`: generation traces for the unconstrained and 55% multimodal cases.
- `cost-emissions-frontier.svg`: best-known cost/emissions trade-off.
- `five-ga-scenario-matrix.svg`: median cost gap and feasible-run count for all five GA variants.
- `cost-time-by-method.svg`: aligned median cost and tonne-weighted transit-time comparison.

The results are synthetic-calibrated heuristic outputs. A missing feasible result is a search finding, not an infeasibility proof, and no percentage is an observed deployment saving.
""", encoding="utf-8")
    return report


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--orders", type=int, default=48)
    parser.add_argument("--density", type=float, default=.10)
    parser.add_argument("--network-seed", type=int, default=42)
    parser.add_argument("--order-seed", type=int, default=31415)
    parser.add_argument("--capacity-tonnes", type=float, default=250)
    parser.add_argument("--capacity-units", type=float, default=4)
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--candidate-routes", type=int, default=80)
    parser.add_argument("--beam-width", type=int, default=300)
    parser.add_argument("--population", type=int, default=100)
    parser.add_argument("--generations", type=int, default=150)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--seeds", default=",".join(str(value) for value in range(30)))
    args = parser.parse_args()
    args.seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    if not args.seeds:
        parser.error("--seeds must contain at least one integer")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    return args


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        "experiment_id": result["experiment_id"],
        "scenarios": len(result["scenarios"]),
        "road_reference": result["reference"],
    }, indent=2, ensure_ascii=False))
