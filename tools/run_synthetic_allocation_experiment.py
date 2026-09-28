#!/usr/bin/env python3
"""Run a transparent 23-city, multi-OD global-allocation stress test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.allocation import (assignment_rank, generate_candidate_pools,
                                solve_exact_allocation, solve_greedy_allocation)
from routing.allocation_ga import solve_allocation_ga
from routing.synthetic import generate_network
from tools.run_allocation_experiment import (COLORS, VARIANTS, method_summary, svg,
                                             write_csv, write_objective_chart)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks" / "synthetic-global-allocation"
SYNTHETIC_VARIANTS = {name: dict(controls) for name, controls in VARIANTS.items()}
SYNTHETIC_VARIANTS["hybrid-seeded"].update(
    mutation_base=1.0, mutation_cap=2.5)


def generate_portfolio(nodes, count, seed):
    """Generate multi-OD demand concentrated on a shared eastbound corridor."""
    rng = random.Random(seed)
    origins = list(range(0, min(5, len(nodes) - 2)))
    destinations = list(range(max(6, len(nodes) - 5), len(nodes)))
    orders = []
    for index in range(count):
        origin_index = rng.choice(origins)
        valid_destinations = [value for value in destinations if value > origin_index]
        destination_index = rng.choice(valid_destinations)
        release = rng.choice((0, 0, 12, 24))
        orders.append({
            "order_id": f"ALLOC-SYN-{index:04d}",
            "origin": nodes[origin_index],
            "destination": nodes[destination_index],
            "release_hour": release,
            "deadline_hours": release + rng.choice((48, 62, 72, 96)),
            "tonnes": rng.choice((20, 40, 85)),
            "shipment_units": 1,
            "container_type": "synthetic-unit",
            "cargo_type": "general",
            "source_type": "synthetic_calibrated",
        })
    return orders


def generate_capacity_resources(config, tonnes, units):
    """Create explicitly synthetic horizon capacities for rail and water."""
    return [{
        "departure_id": f'HORIZON-{edge["id"]}',
        "edge_id": edge["id"],
        "capacity_only": True,
        "capacity_tonnes": tonnes,
        "capacity_units": units,
        "evidence_class": "synthetic_planning_capacity",
    } for edge in config["edges"] if edge["mode"] in {"rail", "water"}]


def write_mode_chart(path, solution, orders):
    counts = {}
    tonnes = {}
    for order, candidate in zip(orders, solution["selected_candidates"]):
        signature = "+".join(candidate["modes"])
        counts[signature] = counts.get(signature, 0) + 1
        tonnes[signature] = tonnes.get(signature, 0) + order["tonnes"]
    maximum = max(tonnes.values())
    body = []
    for index, signature in enumerate(sorted(counts, key=lambda key: (-tonnes[key], key))):
        y = 92 + index * 58
        width = 520 * tonnes[signature] / maximum
        body.append(f'<text x="215" y="{y+20}" text-anchor="end" font-family="sans-serif" font-size="11">{signature}</text>')
        body.append(f'<rect x="230" y="{y}" width="{width:.1f}" height="28" fill="#4c78a8"/>')
        body.append(f'<text x="{245+width:.1f}" y="{y+20}" font-family="sans-serif" font-size="11">{counts[signature]} orders; {tonnes[signature]:g} t</text>')
    path.write_text(svg("Best-known allocation by mode sequence", "".join(body), width=1280,
                        metadata={"data": "best-assignments.csv", "classification": "synthetic_calibrated"}),
                    encoding="utf-8")


def write_convergence_chart(path, traces):
    methods = list(SYNTHETIC_VARIANTS)
    generations = sorted({row["generation"] for row in traces})
    series = {}
    for method in methods:
        series[method] = []
        for generation in generations:
            values = [row["best_objective_cny"] for row in traces
                      if row["method"] == method and row["generation"] == generation
                      and row["best_violation"] == 0]
            series[method].append(sorted(values)[len(values) // 2] if values else None)
    values = [value for rows in series.values() for value in rows if value is not None]
    low, high = min(values), max(values)
    span = max(1, high - low)
    left, top, width, height = 110, 82, 1040, 455
    body = [f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" stroke="#333"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+height}" stroke="#333"/>']
    for method in methods:
        points = []
        for generation, value in zip(generations, series[method]):
            if value is None:
                continue
            x = left + generation / max(1, generations[-1]) * width
            y = top + height - (value - low) / span * height
            points.append(f"{x:.1f},{y:.1f}")
        body.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{COLORS[method]}" stroke-width="2"/>')
    for index, method in enumerate(methods):
        x = 125 + index * 205
        body.append(f'<line x1="{x}" y1="590" x2="{x+24}" y2="590" stroke="{COLORS[method]}" stroke-width="3"/>')
        body.append(f'<text x="{x+30}" y="594" font-family="sans-serif" font-size="11">{method}</text>')
    body.append('<text x="535" y="565" text-anchor="middle" font-family="sans-serif" font-size="13">Generation</text>')
    body.append('<text x="30" y="310" transform="rotate(-90 30 310)" text-anchor="middle" font-family="sans-serif" font-size="13">Median best feasible cost (CNY)</text>')
    path.write_text(svg("Median convergence across seeds", "".join(body), width=1280,
                        metadata={"data": "traces.csv", "aggregation": "median feasible incumbent"}),
                    encoding="utf-8")


def write_capacity_chart(path, solution):
    used = [row for row in solution["capacity_usage"] if row["used_tonnes"] > 0]
    used.sort(key=lambda row: (
        row["used_tonnes"] / row["capacity_tonnes"] if row["capacity_tonnes"] else 0),
              reverse=True)
    rows = used[:12]
    body = []
    for index, row in enumerate(rows):
        y = 75 + index * 43
        ratio = row["used_tonnes"] / row["capacity_tonnes"]
        width = min(1, ratio) * 700
        label = row["departure_id"].replace("HORIZON-e", "e")
        body.append(f'<text x="255" y="{y+17}" text-anchor="end" font-family="sans-serif" font-size="10">{label}</text>')
        body.append(f'<rect x="270" y="{y}" width="700" height="23" fill="#eeeeee"/>')
        body.append(f'<rect x="270" y="{y}" width="{width:.1f}" height="23" fill="#e45756"/>')
        body.append(f'<text x="985" y="{y+17}" font-family="sans-serif" font-size="10">{row["used_tonnes"]:g}/{row["capacity_tonnes"]:g} t</text>')
    path.write_text(svg("Most-used shared capacity resources", "".join(body), width=1280,
                        metadata={"data": "best-capacity.csv", "selection": "top 12 by tonne utilization"}),
                    encoding="utf-8")


def run(args):
    config = generate_network(23, args.density, args.network_seed)
    orders = generate_portfolio(config["nodes"], args.orders, args.order_seed)
    resources = generate_capacity_resources(config, args.capacity_tonnes, args.capacity_units)
    generated = generate_candidate_pools(
        config, orders, resources, top_k=args.top_k, max_routes=args.candidate_routes,
        route_strategy="beam", beam_width=args.beam_width)
    brackets = config["carbon_brackets"]

    oracle_orders = generated["orders"][:args.oracle_orders]
    exact = solve_exact_allocation(
        oracle_orders, generated["candidate_pools"], generated["departures"], brackets,
        max_combinations=1_000_000)
    greedy = solve_greedy_allocation(
        generated["orders"], generated["candidate_pools"], generated["departures"], brackets)
    runs = [{
        "method": "greedy", "seed": None, "status": greedy["status"],
        "feasible": greedy["solution"]["feasible"],
        "total_cost_cny": greedy["solution"]["total_cost_cny"],
        "emissions_kg": greedy["solution"]["emissions_kg"],
        "constraint_violation": greedy["solution"]["constraint_violation"],
        "restarts": 0, "ga_candidate_evaluations": 0,
        "heuristic_seed_evaluations": 0,
        "unique_assignment_evaluations": greedy["candidate_evaluations"],
        "total_solver_evaluations": greedy["candidate_evaluations"],
        "adaptive_control": "not-applicable", "restart_fraction": 0,
        "heuristic_seed_mode": "not-applicable",
        "heuristic_seed_strategy": "deadline",
        "solution": greedy["solution"],
    }]
    traces = []
    for method, controls in SYNTHETIC_VARIANTS.items():
        for seed in args.seeds:
            result = solve_allocation_ga(
                generated["orders"], generated["candidate_pools"], generated["departures"], brackets,
                population=args.population, generations=args.generations, seed=seed,
                patience=args.patience, **controls)
            solution = result["solution"] or result["best_infeasible"]
            runs.append({
                "method": method, "seed": seed, "status": result["status"],
                "feasible": result["solution"] is not None,
                "total_cost_cny": solution["total_cost_cny"],
                "emissions_kg": solution["emissions_kg"],
                "constraint_violation": solution["constraint_violation"],
                "restarts": result["restarts"],
                "ga_candidate_evaluations": result["candidate_evaluations"],
                "heuristic_seed_evaluations": result["heuristic_seed_evaluations"],
                "unique_assignment_evaluations": result["unique_assignment_evaluations"],
                "total_solver_evaluations": result["candidate_evaluations"] + result["heuristic_seed_evaluations"],
                "adaptive_control": result["adaptive_control"],
                "restart_fraction": result["restart_fraction"],
                "heuristic_seed_mode": result["heuristic_seed_mode"],
                "heuristic_seed_strategy": result["heuristic_seed_strategy"],
                "solution": result["solution"],
            })
            traces.extend({"method": method, "seed": seed, **row} for row in result["trace"])

    feasible = [row for row in runs if row["feasible"]]
    if not feasible:
        raise RuntimeError("no method found a feasible synthetic allocation")
    best = min(feasible, key=lambda row: assignment_rank(row["solution"]))
    summaries = method_summary(runs)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "runs.csv", [
        {key: value for key, value in row.items() if key != "solution"} for row in runs])
    write_csv(args.output / "method-summary.csv", summaries)
    write_csv(args.output / "traces.csv", traces)
    assignments = []
    for order, candidate in zip(generated["orders"], best["solution"]["selected_candidates"]):
        assignments.append({
            "method": best["method"], "seed": best["seed"], "order_id": order["order_id"],
            "origin": order["origin"], "destination": order["destination"],
            "tonnes": order["tonnes"], "deadline_hour": order["deadline_hours"],
            "route": ">".join(candidate["route"]), "modes": "+".join(candidate["modes"]),
            "arrival_hour": candidate["arrival_hour"], "noncarbon_cost_cny": candidate["noncarbon_cost_cny"],
            "emissions_kg": candidate["emissions_kg"],
            "capacity_resources": "+".join(row["departure_id"] for row in candidate["capacity_claims"]),
        })
    write_csv(args.output / "best-assignments.csv", assignments)
    write_csv(args.output / "best-capacity.csv", best["solution"]["capacity_usage"])
    write_objective_chart(args.output / "objective-by-method.svg", summaries)
    write_mode_chart(args.output / "mode-allocation.svg", best["solution"], generated["orders"])
    write_convergence_chart(args.output / "convergence.svg", traces)
    write_capacity_chart(args.output / "capacity-use.svg", best["solution"])

    greedy_cost = greedy["solution"]["total_cost_cny"]
    best_cost = best["solution"]["total_cost_cny"]
    report = {
        "experiment_id": "synthetic-23city-global-allocation-v1",
        "data_classification": "synthetic_calibrated",
        "network": {"nodes": len(config["nodes"]), "edges": len(config["edges"]),
                    "density": args.density, "seed": args.network_seed},
        "portfolio": {"orders": len(orders), "tonnes": sum(row["tonnes"] for row in orders),
                      "od_pairs": len({(row["origin"], row["destination"]) for row in orders}),
                      "capacity_resources": len(resources)},
        "candidate_generation": generated["generation_stats"],
        "algorithm_budget": {"seeds": args.seeds, "population": args.population,
                             "generations": args.generations, "patience": args.patience,
                             "variant_controls": SYNTHETIC_VARIANTS},
        "exact_oracle": {"scope": f"first {len(oracle_orders)} orders only",
                         "status": exact["status"], "candidate_evaluations": exact["candidate_evaluations"],
                         "solution": exact["solution"]},
        "method_summary": summaries,
        "best_known_full_portfolio": {"method": best["method"], "seed": best["seed"],
                                      "solution": best["solution"]},
        "greedy_gap_to_best_known_percent": (greedy_cost / best_cost - 1) * 100,
        "best_known_saving_vs_greedy_percent": (greedy_cost - best_cost) / greedy_cost * 100,
        "claims": [
            "All order rows, network edges and shared capacities in this scale test are synthetic calibrated data.",
            "The 23 city names and aggregate distance/mode profile are historical anchors, not a recovered operational graph.",
            "Beam search bounds candidate generation and does not prove that every physical path was considered.",
            "The exact oracle covers only the stated small prefix; the full-portfolio result is best-known heuristic output.",
        ],
    }
    (args.output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "README.md").write_text(f"""# Synthetic 23-city global-allocation stress test

Generated by `python3 -B tools/run_synthetic_allocation_experiment.py`.

The experiment assigns {len(orders)} synthetic orders across {len({(row['origin'], row['destination']) for row in orders})} OD pairs. Each gene selects one bounded route candidate for one order; rail and water edges consume shared planning-horizon capacity. Progressive carbon pricing is applied to the portfolio total.

This is a scale/algorithm experiment, not an operational-data claim. City names and aggregate mode/distance ranges are historical anchors; the rows, edges and capacities are synthetic calibrated inputs. Beam candidate generation and every full-portfolio method are heuristic. Only the first {len(oracle_orders)} orders are exhaustively enumerated.

The reported allocation controller was selected on seeds 30--39, checked on held-out seeds 40--69, and then rerun here on seeds 0--29. The formal best-known result is {best['method']} seed {best['seed']} at CNY {best_cost:,.2f}, {(greedy_cost-best_cost)/greedy_cost*100:.2f}% below the deadline-greedy baseline of CNY {greedy_cost:,.2f}. This comparison is limited to this synthetic instance and does not certify global optimality.

- `results.json`: full scope, settings, small exact oracle and best-known portfolio.
- `runs.csv`, `method-summary.csv`, `traces.csv`: 30-seed method comparison by default.
- `best-assignments.csv`, `best-capacity.csv`: auditable best-known allocation.
- `objective-by-method.svg`, `convergence.svg`, `mode-allocation.svg`, `capacity-use.svg`: result plots.
- Controller selection and independent validation are recorded in `../allocation-control-tuning` and `../allocation-control-validation`.
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
    parser.add_argument("--oracle-orders", type=int, default=5)
    parser.add_argument("--population", type=int, default=100)
    parser.add_argument("--generations", type=int, default=150)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--seeds", default=",".join(str(value) for value in range(30)))
    args = parser.parse_args()
    args.seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    return args


if __name__ == "__main__":
    report = run(parse_args())
    print(json.dumps({
        "experiment_id": report["experiment_id"], "network": report["network"],
        "portfolio": report["portfolio"],
        "best_method": report["best_known_full_portfolio"]["method"],
        "greedy_gap_percent": report["greedy_gap_to_best_known_percent"],
    }, indent=2, ensure_ascii=False))
